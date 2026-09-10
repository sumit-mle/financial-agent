# Salesforce CRM Integration Setup

This guide walks through configuring Salesforce CRM integration for the Financial AI Agent.

## Prerequisites

1. **Salesforce Org**: Production, Sandbox, or Developer Edition
2. **System Administrator** access to create Connected Apps
3. **API Access** enabled for your Salesforce user

## Step 1: Create a Connected App

1. **Login to Salesforce** as System Administrator

2. **Navigate to Setup**:
   - Click the gear icon (⚙️) in top right
   - Select "Setup"

3. **Create Connected App**:
   - In Quick Find, search "App Manager"
   - Click "App Manager"
   - Click "New Connected App"

4. **Basic Information**:
   ```
   Connected App Name: Financial AI Agent
   API Name: Financial_AI_Agent
   Contact Email: your-email@company.com
   Description: AI Agent for customer support and case management
   ```

5. **API (Enable OAuth Settings)**:
   - ✅ Check "Enable OAuth Settings"
   - **Callback URL**: `https://your-domain.com/oauth/callback`
   - **Selected OAuth Scopes**:
     - ✅ Access the identity URL service (id, profile, email, address, phone)
     - ✅ Access and manage your data (api)  
     - ✅ Perform requests on your behalf at any time (refresh_token, offline_access)
     - ✅ Access custom applications (custom_applications)

6. **Save** the Connected App

## Step 2: Configure Security Settings

1. **Edit Policies** (after saving):
   - Click "Manage" on your new Connected App
   - Click "Edit Policies"

2. **OAuth Policies**:
   - **Permitted Users**: Admin approved users are pre-authorized
   - **IP Relaxation**: Relax IP restrictions (or add your server IPs)
   - **Refresh Token Policy**: Refresh token is valid until revoked

3. **Save** the policies

## Step 3: Get API Credentials

1. **Consumer Key & Secret**:
   - Go back to your Connected App
   - Click "View" next to Consumer Key
   - Copy the **Consumer Key** (this is CLIENT_ID)
   - Click "Click to reveal" for Consumer Secret
   - Copy the **Consumer Secret** (this is CLIENT_SECRET)

2. **Security Token**:
   - Go to your personal settings (click your profile photo → Settings)
   - In Quick Find: "Reset My Security Token"
   - Click "Reset Security Token"
   - Check your email for the new security token

## Step 4: Configure Environment Variables

Add these to your `.env` file:

```bash
# Salesforce CRM Integration
SALESFORCE_USERNAME="your-username@company.com"
SALESFORCE_PASSWORD="your-password-plus-security-token"  
SALESFORCE_CLIENT_ID="your-consumer-key-from-connected-app"
SALESFORCE_CLIENT_SECRET="your-consumer-secret-from-connected-app"
SALESFORCE_DOMAIN="login"  # or "test" for sandbox
```

**Important**: The password should be your Salesforce password + security token concatenated.
Example: If password is "mypass123" and token is "ABC123DEF456", use "mypass123ABC123DEF456"

## Step 5: Required Salesforce Objects & Fields

The AI Agent expects these standard and custom objects:

### Custom Fields on Standard Objects

**Account Object**:
```
Customer_ID__c (Text, External ID, Unique)
```

**Case Object**: 
```
Customer_ID__c (Text, External ID)
```

### Create Custom Fields

1. **Account Custom Field**:
   - Setup → Object Manager → Account
   - Fields & Relationships → New
   - Data Type: Text
   - Field Label: Customer ID
   - Field Name: Customer_ID
   - Length: 50
   - ✅ External ID
   - ✅ Unique (Case Insensitive)

2. **Case Custom Field**:
   - Setup → Object Manager → Case  
   - Fields & Relationships → New
   - Data Type: Text
   - Field Label: Customer ID
   - Field Name: Customer_ID
   - Length: 50
   - ✅ External ID

## Step 6: Test Integration

1. **Start the API** with Salesforce credentials configured

2. **Check Health Endpoint**:
   ```bash
   curl http://localhost:8000/api/v1/admin/health
   ```
   
   Should show:
   ```json
   {
     "status": "ok",
     "services": {
       "salesforce": "ok"
     }
   }
   ```

3. **Test Account Lookup**:
   ```bash
   curl -X POST http://localhost:8000/api/v1/chat \
     -H "Content-Type: application/json" \
     -d '{
       "message": "Look up my account information",
       "customer_id": "test-customer-123"
     }'
   ```

## Troubleshooting

### Authentication Errors

**"Invalid username, password, security token"**:
- Verify username is correct
- Ensure password + security token are concatenated
- Reset security token if needed
- Check IP restrictions in Connected App

**"Invalid client_id"**:
- Verify Consumer Key is correct
- Ensure Connected App is active

### Permission Errors

**"insufficient access rights"**:
- Verify user has API access enabled
- Check profile permissions for Account/Case objects
- Ensure user can read/write custom fields

### Network Errors

**Connection timeouts**:
- Check firewall settings
- Verify Salesforce domain (login.salesforce.com vs test.salesforce.com)
- Try different OAuth endpoints

## Production Considerations

1. **Security**:
   - Use dedicated integration user account
   - Apply principle of least privilege  
   - Regularly rotate security tokens
   - Monitor API usage limits

2. **Performance**:
   - Implement connection pooling
   - Cache authentication tokens
   - Use bulk APIs for large operations
   - Monitor API call limits (24-hour rolling window)

3. **Monitoring**:
   - Set up login history monitoring
   - Configure API usage alerts
   - Track failed authentication attempts
   - Monitor case creation rates

## API Limits

- **Daily API Calls**: Varies by Salesforce edition
- **Concurrent Requests**: 25 per organization
- **Rate Limiting**: 10 requests per 20 seconds per user

Monitor usage via Setup → System Overview → API Usage.

## Support

For Salesforce-specific issues:
- [Salesforce Developer Documentation](https://developer.salesforce.com/docs)
- [Connected Apps Guide](https://help.salesforce.com/s/articleView?id=sf.connected_app_overview.htm)
- [API Documentation](https://developer.salesforce.com/docs/api-explorer)