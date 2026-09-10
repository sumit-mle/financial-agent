"""
Salesforce CRM integration for Financial AI Agent.

Production-grade Salesforce connector with:
- OAuth2 authentication with refresh token handling
- Case management (complaints, inquiries)
- Account and contact lookup
- Error handling and retry logic
- Metrics collection

Configuration:
- SALESFORCE_USERNAME: Salesforce username
- SALESFORCE_PASSWORD: Salesforce password + security token
- SALESFORCE_CLIENT_ID: Connected app consumer key
- SALESFORCE_CLIENT_SECRET: Connected app consumer secret
- SALESFORCE_DOMAIN: Instance domain (e.g., 'login' or custom domain)
"""
import asyncio
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests

from app.core.config import settings
from app.core.logging import get_logger
from app.observability.metrics import record_vector_operation, track_model_inference

logger = get_logger(__name__)

# Salesforce is an *optional* integration (it reports "not_configured" when no
# credentials are set). Import its SDK defensively so a slim install without
# simple-salesforce cannot break the import chain that reaches the chat API:
#   salesforce → actions.connectors → action_node → agent.graph → routes.chat → main
try:
    from simple_salesforce import Salesforce, format_soql
    from simple_salesforce.exceptions import SalesforceError

    SALESFORCE_SDK_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only in slim installs
    Salesforce = None  # type: ignore[assignment,misc]
    format_soql = None  # type: ignore[assignment]

    class SalesforceError(Exception):  # type: ignore[no-redef]
        """Fallback so `except SalesforceError` stays valid without the SDK."""

    SALESFORCE_SDK_AVAILABLE = False
    logger.info(
        "simple-salesforce is not installed — the Salesforce integration is "
        "disabled. Install it to enable CRM case management."
    )

class SalesforceClient:
    """
    Production Salesforce client with authentication, error handling, and metrics.
    """
    
    def __init__(self):
        self.sf: Optional["Salesforce"] = None
        self.last_auth_time: Optional[float] = None
        self.auth_expiry_buffer = 300  # Re-auth 5 mins before token expiry
        self._lock = asyncio.Lock()

    async def _authenticate(self) -> None:
        """Authenticate with Salesforce using OAuth2."""
        try:
            if not SALESFORCE_SDK_AVAILABLE:
                raise RuntimeError(
                    "simple-salesforce is not installed; cannot authenticate. "
                    "Install it (see requirements.txt) to use the CRM integration."
                )

            # Use environment variables or settings
            username = getattr(settings, 'salesforce_username', None)
            password = getattr(settings, 'salesforce_password', None)
            client_id = getattr(settings, 'salesforce_client_id', None)
            client_secret = getattr(settings, 'salesforce_client_secret', None)
            domain = getattr(settings, 'salesforce_domain', 'login')
            
            if not all([username, password, client_id, client_secret]):
                raise ValueError("Missing Salesforce credentials in environment")
            
            # Run Salesforce auth in thread pool (it's sync)
            loop = asyncio.get_event_loop()
            self.sf = await loop.run_in_executor(
                None, 
                lambda: Salesforce(
                    username=username,
                    password=password,
                    consumer_key=client_id,
                    consumer_secret=client_secret,
                    domain=domain
                )
            )
            
            self.last_auth_time = time.time()
            logger.info("✅ Salesforce authentication successful")
            
        except Exception as e:
            logger.error(f"❌ Salesforce authentication failed: {e}")
            raise

    async def _ensure_authenticated(self) -> None:
        """Ensure we have a valid Salesforce session."""
        async with self._lock:
            should_reauth = (
                self.sf is None or 
                self.last_auth_time is None or
                (time.time() - self.last_auth_time) > (3600 - self.auth_expiry_buffer)  # 1hr - buffer
            )
            
            if should_reauth:
                await self._authenticate()

    @track_model_inference("salesforce", "account_lookup")
    async def lookup_account(self, customer_id: str) -> Dict[str, Any]:
        """
        Look up customer account information by customer ID.
        
        Maps to Salesforce Account and Contact objects.
        """
        await self._ensure_authenticated()
        
        try:
            loop = asyncio.get_event_loop()
            
            # Query Account by external customer ID.
            # format_soql safely quotes + escapes the bind value (SOQL injection guard).
            account_query = format_soql(
                """
                SELECT Id, Name, AccountNumber, Type, Phone, BillingAddress,
                       CreatedDate, LastModifiedDate, AccountSource
                FROM Account
                WHERE Customer_ID__c = {}
                LIMIT 1
                """,
                customer_id,
            )
            
            account_result = await loop.run_in_executor(
                None, 
                lambda: self.sf.query(account_query)
            )
            
            if not account_result['records']:
                return {
                    "customer_id": customer_id,
                    "found": False,
                    "error": "Customer not found in Salesforce"
                }
            
            account = account_result['records'][0]
            account_id = account['Id']
            
            # Query related contacts
            contact_query = format_soql(
                """
                SELECT Id, FirstName, LastName, Email, Phone, MailingAddress
                FROM Contact
                WHERE AccountId = {}
                LIMIT 5
                """,
                account_id,
            )
            
            contacts = await loop.run_in_executor(
                None,
                lambda: self.sf.query(contact_query)
            )
            
            # Query recent cases for this account
            case_query = format_soql(
                """
                SELECT Id, CaseNumber, Subject, Status, Priority, CreatedDate, Type
                FROM Case
                WHERE AccountId = {}
                ORDER BY CreatedDate DESC
                LIMIT 10
                """,
                account_id,
            )
            
            cases = await loop.run_in_executor(
                None,
                lambda: self.sf.query(case_query)
            )
            
            # Format response
            result = {
                "customer_id": customer_id,
                "found": True,
                "account": {
                    "id": account.get('Id'),
                    "name": account.get('Name'),
                    "account_number": account.get('AccountNumber'),
                    "type": account.get('Type'),
                    "phone": account.get('Phone'),
                    "created_date": account.get('CreatedDate'),
                    "last_modified": account.get('LastModifiedDate'),
                    "source": account.get('AccountSource')
                },
                "contacts": [
                    {
                        "id": contact.get('Id'),
                        "name": f"{contact.get('FirstName', '')} {contact.get('LastName', '')}".strip(),
                        "email": contact.get('Email'),
                        "phone": contact.get('Phone')
                    }
                    for contact in contacts['records']
                ],
                "recent_cases": [
                    {
                        "id": case.get('Id'),
                        "case_number": case.get('CaseNumber'),
                        "subject": case.get('Subject'),
                        "status": case.get('Status'),
                        "priority": case.get('Priority'),
                        "type": case.get('Type'),
                        "created_date": case.get('CreatedDate')
                    }
                    for case in cases['records']
                ]
            }
            
            record_vector_operation("account_lookup", "salesforce", True)
            return result
            
        except SalesforceError as e:
            logger.error(f"Salesforce API error in account lookup: {e}")
            record_vector_operation("account_lookup", "salesforce", False)
            return {
                "customer_id": customer_id,
                "found": False,
                "error": f"Salesforce error: {e}"
            }
        except Exception as e:
            logger.error(f"Unexpected error in Salesforce account lookup: {e}")
            record_vector_operation("account_lookup", "salesforce", False)
            raise

    @track_model_inference("salesforce", "case_creation")
    async def create_case(
        self, 
        customer_id: str, 
        subject: str, 
        description: str, 
        case_type: str = "Complaint",
        priority: str = "Medium"
    ) -> Dict[str, Any]:
        """
        Create a new case (complaint/inquiry) in Salesforce.
        """
        await self._ensure_authenticated()
        
        try:
            loop = asyncio.get_event_loop()
            
            # First, find the account ID
            account_lookup = await self.lookup_account(customer_id)
            
            if not account_lookup.get('found'):
                return {
                    "success": False,
                    "error": "Customer account not found",
                    "customer_id": customer_id
                }
            
            account_id = account_lookup['account']['id']
            
            # Create case data
            case_data = {
                'AccountId': account_id,
                'Subject': subject[:255],  # Salesforce field limit
                'Description': description,
                'Type': case_type,
                'Priority': priority,
                'Status': 'New',
                'Origin': 'AI Agent',
                'Customer_ID__c': customer_id  # Custom field
            }
            
            # Create the case
            result = await loop.run_in_executor(
                None,
                lambda: self.sf.Case.create(case_data)
            )
            
            case_id = result['id']
            
            # Query the created case to get case number
            case_query = format_soql(
                """
                SELECT Id, CaseNumber, Subject, Status, Priority, CreatedDate
                FROM Case
                WHERE Id = {}
                """,
                case_id,
            )
            
            case_details = await loop.run_in_executor(
                None,
                lambda: self.sf.query(case_query)
            )
            
            case_record = case_details['records'][0] if case_details['records'] else {}
            
            record_vector_operation("case_creation", "salesforce", True)
            
            return {
                "success": True,
                "case_id": case_id,
                "case_number": case_record.get('CaseNumber'),
                "customer_id": customer_id,
                "subject": subject,
                "status": case_record.get('Status', 'New'),
                "priority": case_record.get('Priority', priority),
                "created_date": case_record.get('CreatedDate')
            }
            
        except SalesforceError as e:
            logger.error(f"Salesforce API error in case creation: {e}")
            record_vector_operation("case_creation", "salesforce", False)
            return {
                "success": False,
                "error": f"Salesforce error: {e}",
                "customer_id": customer_id
            }
        except Exception as e:
            logger.error(f"Unexpected error in Salesforce case creation: {e}")
            record_vector_operation("case_creation", "salesforce", False)
            raise

    @track_model_inference("salesforce", "case_lookup")
    async def lookup_case_status(self, case_number: str) -> Dict[str, Any]:
        """
        Look up case status by case number.
        """
        await self._ensure_authenticated()
        
        try:
            loop = asyncio.get_event_loop()
            
            # Query case by case number
            case_query = format_soql(
                """
                SELECT Id, CaseNumber, Subject, Description, Status, Priority,
                       Type, CreatedDate, LastModifiedDate, Owner.Name,
                       Account.Name, Customer_ID__c
                FROM Case
                WHERE CaseNumber = {}
                LIMIT 1
                """,
                case_number,
            )
            
            result = await loop.run_in_executor(
                None,
                lambda: self.sf.query(case_query)
            )
            
            if not result['records']:
                return {
                    "case_number": case_number,
                    "found": False,
                    "error": "Case not found"
                }
            
            case = result['records'][0]
            
            # Get case comments/history
            case_id = case['Id']
            comment_query = format_soql(
                """
                SELECT Id, CommentBody, CreatedDate, CreatedBy.Name
                FROM CaseComment
                WHERE ParentId = {}
                ORDER BY CreatedDate DESC
                LIMIT 5
                """,
                case_id,
            )
            
            comments = await loop.run_in_executor(
                None,
                lambda: self.sf.query(comment_query)
            )
            
            record_vector_operation("case_lookup", "salesforce", True)
            
            return {
                "case_number": case_number,
                "found": True,
                "case": {
                    "id": case.get('Id'),
                    "subject": case.get('Subject'),
                    "description": case.get('Description'),
                    "status": case.get('Status'),
                    "priority": case.get('Priority'),
                    "type": case.get('Type'),
                    "created_date": case.get('CreatedDate'),
                    "last_modified": case.get('LastModifiedDate'),
                    "owner": case.get('Owner', {}).get('Name') if case.get('Owner') else None,
                    "account_name": case.get('Account', {}).get('Name') if case.get('Account') else None,
                    "customer_id": case.get('Customer_ID__c')
                },
                "recent_comments": [
                    {
                        "body": comment.get('CommentBody'),
                        "created_date": comment.get('CreatedDate'),
                        "created_by": comment.get('CreatedBy', {}).get('Name') if comment.get('CreatedBy') else None
                    }
                    for comment in comments['records']
                ]
            }
            
        except SalesforceError as e:
            logger.error(f"Salesforce API error in case lookup: {e}")
            record_vector_operation("case_lookup", "salesforce", False)
            return {
                "case_number": case_number,
                "found": False,
                "error": f"Salesforce error: {e}"
            }
        except Exception as e:
            logger.error(f"Unexpected error in Salesforce case lookup: {e}")
            record_vector_operation("case_lookup", "salesforce", False)
            raise

    @track_model_inference("salesforce", "case_update") 
    async def update_case_status(self, case_id: str, status: str, comment: Optional[str] = None) -> Dict[str, Any]:
        """
        Update case status and optionally add a comment.
        """
        await self._ensure_authenticated()
        
        try:
            loop = asyncio.get_event_loop()
            
            # Update case status
            update_data = {'Status': status}
            
            await loop.run_in_executor(
                None,
                lambda: self.sf.Case.update(case_id, update_data)
            )
            
            # Add comment if provided
            if comment:
                comment_data = {
                    'ParentId': case_id,
                    'CommentBody': comment,
                    'IsPublished': True
                }
                
                await loop.run_in_executor(
                    None,
                    lambda: self.sf.CaseComment.create(comment_data)
                )
            
            record_vector_operation("case_update", "salesforce", True)
            
            return {
                "success": True,
                "case_id": case_id,
                "new_status": status,
                "comment_added": comment is not None,
                "updated_at": datetime.utcnow().isoformat()
            }
            
        except SalesforceError as e:
            logger.error(f"Salesforce API error in case update: {e}")
            record_vector_operation("case_update", "salesforce", False)
            return {
                "success": False,
                "case_id": case_id,
                "error": f"Salesforce error: {e}"
            }
        except Exception as e:
            logger.error(f"Unexpected error in Salesforce case update: {e}")
            record_vector_operation("case_update", "salesforce", False)
            raise

    async def health_check(self) -> Dict[str, Any]:
        """
        Health check for Salesforce connectivity.
        """
        try:
            await self._ensure_authenticated()
            
            # Simple query to test connectivity
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self.sf.query("SELECT Id FROM Organization LIMIT 1")
            )
            
            return {
                "status": "healthy",
                "authenticated": True,
                "org_id": result['records'][0]['Id'] if result['records'] else None,
                "last_auth_time": self.last_auth_time
            }
            
        except Exception as e:
            logger.error(f"Salesforce health check failed: {e}")
            return {
                "status": "unhealthy",
                "authenticated": False,
                "error": str(e),
                "last_auth_time": self.last_auth_time
            }


# Global client instance
_salesforce_client: Optional[SalesforceClient] = None

def get_salesforce_client() -> SalesforceClient:
    """Get singleton Salesforce client."""
    global _salesforce_client
    if _salesforce_client is None:
        _salesforce_client = SalesforceClient()
    return _salesforce_client