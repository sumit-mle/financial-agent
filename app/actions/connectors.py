"""
Action Connectors — concrete implementations of all agent actions.

Production mode: Uses real Salesforce CRM integration for customer data, cases, and complaints.
Development mode: Falls back to mock responses for testing without external dependencies.

Architecture:
- Primary: Salesforce CRM via simple-salesforce library
- Fallback: Mock responses when Salesforce unavailable or in dev mode
- Metrics: All operations tracked via Prometheus metrics

Environment Variables:
- SALESFORCE_USERNAME, SALESFORCE_PASSWORD, SALESFORCE_CLIENT_ID, SALESFORCE_CLIENT_SECRET
- CRM_API_URL, TICKETING_API_URL, NOTIFICATION_API_URL (legacy fallbacks)
"""
import random
import uuid
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.actions.registry import ActionSpec, register
from app.core.config import settings
from app.core.logging import get_logger
from app.integrations.salesforce import get_salesforce_client
from app.observability.metrics import record_vector_operation

logger = get_logger(__name__)

# ── HTTP client (shared, async) ───────────────────────────────────────────────
_http = httpx.AsyncClient(timeout=10.0)


def _is_dev() -> bool:
    """Check if we're in development mode or missing Salesforce credentials."""
    return (
        not settings.is_production or 
        not all([
            settings.salesforce_username,
            settings.salesforce_password, 
            settings.salesforce_client_id,
            settings.salesforce_client_secret
        ])
    )


def _use_salesforce() -> bool:
    """Check if we should use Salesforce integration."""
    return not _is_dev()


# ── CRM Actions ───────────────────────────────────────────────────────────────

async def lookup_account_summary(customer_id: str) -> dict[str, Any]:
    """Fetch customer account summary from CRM."""
    
    if _use_salesforce():
        try:
            sf_client = get_salesforce_client()
            result = await sf_client.lookup_account(customer_id)
            
            if result.get('found'):
                # Transform Salesforce data to standardized format
                account = result['account']
                return {
                    "customer_id": customer_id,
                    "name": account.get('name'),
                    "account_status": "active",  # Could map from Salesforce status field
                    "products": [case.get('type', 'General') for case in result.get('recent_cases', [])[:3]],
                    "account_number": account.get('account_number'),
                    "phone": account.get('phone'),
                    "open_complaints": len([case for case in result.get('recent_cases', []) 
                                           if case.get('status') not in ['Closed', 'Resolved']]),
                    "account_since": account.get('created_date', '').split('T')[0] if account.get('created_date') else None,
                    "last_activity": account.get('last_modified', '').split('T')[0] if account.get('last_modified') else None,
                    "salesforce_data": True,
                    "contacts": result.get('contacts', [])
                }
            else:
                record_vector_operation("account_lookup", "salesforce", False)
                logger.warning(f"Customer {customer_id} not found in Salesforce")
                
        except Exception as e:
            logger.error(f"Salesforce lookup failed for {customer_id}: {e}")
            record_vector_operation("account_lookup", "salesforce", False)
            # Fall through to mock data
    
    # Development mode or Salesforce fallback
    if _is_dev():
        # Deterministic mock based on customer_id hash
        seed = abs(hash(customer_id)) % 100_000
        return {
            "customer_id": customer_id,
            "name": f"Customer {seed}",
            "account_status": "active",
            "products": ["Checking Account", "Visa Credit Card"],
            "credit_score": 680 + (seed % 120),
            "open_complaints": seed % 3,
            "account_since": "2019-03-15",
            "last_activity": (datetime.utcnow() - timedelta(days=seed % 30)).strftime("%Y-%m-%d"),
            "salesforce_data": False
        }
    
    # Legacy HTTP API fallback
    resp = await _http.get(f"{settings.crm_api_url}/accounts/{customer_id}")
    resp.raise_for_status()
    return resp.json()


async def lookup_transaction_history(customer_id: str, days: int = 30) -> dict[str, Any]:
    """Fetch recent transaction history."""
    # Note: Salesforce typically doesn't store transaction data - would integrate with core banking
    # For now, use mock data or external banking API
    
    if _is_dev():
        seed = abs(hash(customer_id)) % 100
        transactions = [
            {
                "id": f"TXN{i:04d}",
                "date": (datetime.utcnow() - timedelta(days=i * 2)).strftime("%Y-%m-%d"),
                "description": random.choice([  # noqa: S311
                    "AMAZON.COM", "STARBUCKS", "WALMART", "NETFLIX", "ATM WITHDRAWAL"
                ]),
                "amount": round(10 + (i * 7.35) % 200, 2),
                "type": "debit" if i % 4 != 0 else "credit",
                "status": "completed",
            }
            for i in range(1, min(days // 2 + 1, 15))
        ]
        return {"customer_id": customer_id, "transactions": transactions, "period_days": days}
    
    resp = await _http.get(
        f"{settings.crm_api_url}/accounts/{customer_id}/transactions",
        params={"days": days},
    )
    resp.raise_for_status()
    return resp.json()


# ── Complaint Actions ─────────────────────────────────────────────────────────

async def lookup_complaint_status(complaint_id: str) -> dict[str, Any]:
    """Look up the status of an existing complaint."""
    
    if _use_salesforce():
        try:
            sf_client = get_salesforce_client()
            result = await sf_client.lookup_case_status(complaint_id)
            
            if result.get('found'):
                case = result['case']
                return {
                    "complaint_id": complaint_id,
                    "status": case.get('status'),
                    "filed_date": case.get('created_date', '').split('T')[0] if case.get('created_date') else None,
                    "last_updated": case.get('last_modified', '').split('T')[0] if case.get('last_modified') else None,
                    "assigned_to": case.get('owner'),
                    "subject": case.get('subject'),
                    "priority": case.get('priority'),
                    "case_type": case.get('type'),
                    "account_name": case.get('account_name'),
                    "recent_comments": result.get('recent_comments', []),
                    "salesforce_data": True
                }
            else:
                logger.warning(f"Case {complaint_id} not found in Salesforce")
                
        except Exception as e:
            logger.error(f"Salesforce case lookup failed for {complaint_id}: {e}")
            # Fall through to mock
    
    # Development mode or Salesforce fallback
    if _is_dev():
        statuses = ["Under Review", "Pending Response", "Resolved", "Escalated to Supervisor"]
        seed = abs(hash(complaint_id)) % 4
        return {
            "complaint_id": complaint_id,
            "status": statuses[seed],
            "filed_date": "2024-11-15",
            "last_updated": "2024-12-01",
            "assigned_to": f"Agent #{1000 + seed * 23}",
            "expected_resolution": (datetime.utcnow() + timedelta(days=5)).strftime("%Y-%m-%d"),
            "notes": "Under active review. You will be notified via email within 5 business days.",
            "salesforce_data": False
        }
    
    resp = await _http.get(f"{settings.ticketing_api_url}/complaints/{complaint_id}")
    resp.raise_for_status()
    return resp.json()


async def create_complaint_ticket(
    customer_id: str,
    issue_description: str,
    product: str,
) -> dict[str, Any]:
    """Create a new complaint ticket in the ticketing system."""
    
    if _use_salesforce():
        try:
            sf_client = get_salesforce_client()
            
            # Map product to Salesforce case type
            case_type_map = {
                "credit_card": "Credit Card",
                "checking": "Checking Account", 
                "savings": "Savings Account",
                "loan": "Loan",
                "mortgage": "Mortgage"
            }
            case_type = case_type_map.get(product.lower(), "General Inquiry")
            
            result = await sf_client.create_case(
                customer_id=customer_id,
                subject=f"{product} Issue: {issue_description[:50]}...",
                description=issue_description,
                case_type=case_type,
                priority="Medium"
            )
            
            if result.get('success'):
                return {
                    "ticket_id": result.get('case_number'),
                    "case_id": result.get('case_id'),
                    "customer_id": customer_id,
                    "product": product,
                    "issue": issue_description[:200],
                    "status": result.get('status', 'New'),
                    "priority": result.get('priority', 'Medium'),
                    "created_at": result.get('created_date'),
                    "reference_number": result.get('case_number'),
                    "salesforce_data": True
                }
            else:
                logger.error(f"Salesforce case creation failed: {result.get('error')}")
                
        except Exception as e:
            logger.error(f"Salesforce case creation error: {e}")
            # Fall through to mock
    
    # Development mode or Salesforce fallback
    ticket_id = f"CMP-{uuid.uuid4().hex[:8].upper()}"
    if _is_dev():
        return {
            "ticket_id": ticket_id,
            "customer_id": customer_id,
            "product": product,
            "issue": issue_description[:200],
            "status": "Open",
            "priority": "Medium",
            "created_at": datetime.utcnow().isoformat(),
            "expected_response_days": 5,
            "reference_number": ticket_id,
            "salesforce_data": False
        }
    
    payload = {
        "customer_id": customer_id,
        "issue_description": issue_description,
        "product": product,
    }
    resp = await _http.post(f"{settings.ticketing_api_url}/complaints", json=payload)
    resp.raise_for_status()
    return resp.json()


async def update_complaint_status(complaint_id: str, status: str) -> dict[str, Any]:
    """Update the status of an existing complaint."""
    
    if _use_salesforce():
        try:
            sf_client = get_salesforce_client()
            
            # First lookup to get case ID
            case_lookup = await sf_client.lookup_case_status(complaint_id)
            if case_lookup.get('found'):
                case_id = case_lookup['case']['id']
                
                result = await sf_client.update_case_status(
                    case_id=case_id,
                    status=status,
                    comment=f"Status updated to {status} via AI Agent"
                )
                
                if result.get('success'):
                    return {
                        "complaint_id": complaint_id,
                        "updated_status": status,
                        "updated_at": result.get('updated_at'),
                        "success": True,
                        "salesforce_data": True
                    }
            
        except Exception as e:
            logger.error(f"Salesforce case update error: {e}")
            # Fall through to mock
    
    # Development mode or Salesforce fallback
    if _is_dev():
        return {
            "complaint_id": complaint_id,
            "updated_status": status,
            "updated_at": datetime.utcnow().isoformat(),
            "success": True,
            "salesforce_data": False
        }
    
    resp = await _http.patch(
        f"{settings.ticketing_api_url}/complaints/{complaint_id}",
        json={"status": status},
    )
    resp.raise_for_status()
    return resp.json()


# ── Payment Actions ───────────────────────────────────────────────────────────

async def reschedule_payment(customer_id: str, new_date: str) -> dict[str, Any]:
    """Reschedule an upcoming payment to a new date."""
    if _is_dev():
        return {
            "customer_id": customer_id,
            "confirmation_id": f"PMT-{uuid.uuid4().hex[:8].upper()}",
            "new_payment_date": new_date,
            "original_amount": 245.00,
            "status": "Rescheduled",
            "confirmation_sent_to": "customer@email.com",
        }
    resp = await _http.post(
        f"{settings.crm_api_url}/accounts/{customer_id}/reschedule-payment",
        json={"new_date": new_date},
    )
    resp.raise_for_status()
    return resp.json()


# ── Notification Actions ──────────────────────────────────────────────────────

async def send_notification(customer_id: str, message: str) -> dict[str, Any]:
    """Send a notification to the customer (email/SMS)."""
    if _is_dev():
        return {
            "customer_id": customer_id,
            "notification_id": f"NTF-{uuid.uuid4().hex[:8].upper()}",
            "channel": "email",
            "status": "queued",
            "queued_at": datetime.utcnow().isoformat(),
        }
    resp = await _http.post(
        f"{settings.notification_api_url}/send",
        json={"customer_id": customer_id, "message": message},
    )
    resp.raise_for_status()
    return resp.json()


async def escalate_to_human(reason: str, conversation_summary: str) -> dict[str, Any]:
    """Create an escalation ticket for human agent assignment."""
    escalation_id = f"ESC-{uuid.uuid4().hex[:8].upper()}"
    if _is_dev():
        return {
            "escalation_id": escalation_id,
            "reason": reason,
            "summary": conversation_summary[:500],
            "assigned_queue": "Tier-2 Support",
            "estimated_wait_minutes": 8,
            "status": "queued",
            "created_at": datetime.utcnow().isoformat(),
        }
    resp = await _http.post(
        f"{settings.ticketing_api_url}/escalations",
        json={"reason": reason, "summary": conversation_summary},
    )
    resp.raise_for_status()
    return resp.json()


# ── Register all actions ──────────────────────────────────────────────────────
# This runs at import time, populating the global registry.

register(ActionSpec(
    name="lookup_account_summary",
    description="Fetch customer account summary including products and status",
    parameters={"customer_id": "The customer's unique identifier"},
    required_params=["customer_id"],
    fn=lookup_account_summary,
    category="crm",
))

register(ActionSpec(
    name="lookup_transaction_history",
    description="Fetch recent transaction history for a customer",
    parameters={
        "customer_id": "The customer's unique identifier",
        "days": "Number of days of history to retrieve (default: 30)",
    },
    required_params=["customer_id"],
    fn=lookup_transaction_history,
    category="crm",
))

register(ActionSpec(
    name="lookup_complaint_status",
    description="Get the current status of an existing complaint",
    parameters={"complaint_id": "The complaint or case reference number"},
    required_params=["complaint_id"],
    fn=lookup_complaint_status,
    category="complaint",
))

register(ActionSpec(
    name="create_complaint_ticket",
    description="File a new complaint ticket in the system",
    parameters={
        "customer_id": "The customer's unique identifier",
        "issue_description": "Detailed description of the complaint",
        "product": "Financial product the complaint is about",
    },
    required_params=["customer_id", "issue_description", "product"],
    fn=create_complaint_ticket,
    category="complaint",
))

register(ActionSpec(
    name="update_complaint_status",
    description="Update the status of an existing complaint",
    parameters={
        "complaint_id": "The complaint reference number",
        "status": "New status (e.g. 'Pending Customer Response', 'Resolved')",
    },
    required_params=["complaint_id", "status"],
    fn=update_complaint_status,
    category="complaint",
))

register(ActionSpec(
    name="reschedule_payment",
    description="Reschedule an upcoming payment to a new date",
    parameters={
        "customer_id": "The customer's unique identifier",
        "new_date": "New payment date in YYYY-MM-DD format",
    },
    required_params=["customer_id", "new_date"],
    fn=reschedule_payment,
    category="billing",
))

register(ActionSpec(
    name="send_notification",
    description="Send an email or SMS notification to the customer",
    parameters={
        "customer_id": "The customer's unique identifier",
        "message": "Notification message content",
    },
    required_params=["customer_id", "message"],
    fn=send_notification,
    category="notification",
))

register(ActionSpec(
    name="escalate_to_human",
    description="Escalate to a human agent with full conversation context",
    parameters={
        "reason": "Reason for escalation",
        "conversation_summary": "Brief summary of the conversation for the human agent",
    },
    required_params=["reason", "conversation_summary"],
    fn=escalate_to_human,
    category="crm",
))
