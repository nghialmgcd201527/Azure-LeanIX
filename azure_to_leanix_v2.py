# LeanIX Azure Integration Script

import requests
import base64
import json
import logging
import sys
import urllib.parse
from datetime import datetime
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.subscription import SubscriptionClient
from azure.identity import DefaultAzureCredential

# Configure logging
logger = logging.getLogger("leanix_integration")
logger.setLevel(logging.DEBUG)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Configuration
LEANIX_API_BASE_URL = "https://vinfast.leanix.net"
LEANIX_API_TOKEN = "xxxxx"

# Application mapping - Update this with your Azure project to application mapping
PROJECT_APP_MAPPING = {
    "123": "Auth0-CA",
    "ABC": "Auth0-EU",
    "huhu": "Auth0-US",
    "hihi": "Auth0-VN",
    "xemay": "Auth0-AS",
    "xedap": "Azure AD-Vingroup",
    "xetai": "Battery Swap App",
    "xeoto": "Car Tracker",
    "xebo": "Connected Car Portal-AS",
    "xeheo": "Connected Car Portal-CA"
}

def get_current_date():
    """Get current date in YYYY-MM-DD format"""
    return datetime.now().strftime("%Y-%m-%d")

def get_current_timestamp():
    """Get current timestamp in YYYY-MM-DD HH:MM:SS format"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def get_current_user():
    """Get current user, defaults to system user if not available"""
    try:
        import getpass
        return getpass.getuser()
    except:
        return "system"

def get_leanix_token():
    """Get authentication token from LeanIX API"""
    auth_url = f"{LEANIX_API_BASE_URL}/services/mtm/v1/oauth2/token"
    
    auth_string = f"apitoken:{LEANIX_API_TOKEN}"
    auth_header = base64.b64encode(auth_string.encode()).decode()
    
    headers = {
        'Authorization': f'Basic {auth_header}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    data = {
        'grant_type': 'client_credentials'
    }
    
    try:
        response = requests.post(auth_url, headers=headers, data=data)
        response.raise_for_status()
        return response.json().get('access_token')
    except Exception as e:
        logger.error(f"Error getting token: {str(e)}")
        if hasattr(response, 'text'):
            logger.error(f"Response text: {response.text}")
        raise

def list_azure_resources():
    """List Azure resources with project tags"""
    resources = []
    
    try:
        # Use DefaultAzureCredential which works in Cloud Shell
        credential = DefaultAzureCredential()
        
        # Get all subscriptions
        subscription_client = SubscriptionClient(credential)
        subscriptions = list(subscription_client.subscriptions.list())
        
        logger.info(f"Found {len(subscriptions)} Azure subscriptions")
        
        for subscription in subscriptions:
            subscription_id = subscription.subscription_id
            logger.info(f"Processing subscription: {subscription.display_name} ({subscription_id})")
            
            # Create a client to work with resources in this subscription
            resource_client = ResourceManagementClient(credential, subscription_id)
            
            # List all resources in the subscription
            for resource in resource_client.resources.list():
                # Try to get resource tags
                tags = resource.tags or {}
                
                # Check if resource has a project tag that maps to an application
                project_tag = None
                for key, value in tags.items():
                    if key.lower() == 'project' and value in PROJECT_APP_MAPPING:
                        project_tag = value
                        break
                
                if project_tag:
                    # Extract resource type parts
                    provider = resource.type.split('/')[0]  # e.g., 'Microsoft.Compute'
                    service_type = resource.type.split('/')[-1]  # e.g., 'virtualMachines'
                    
                    resource_info = {
                        'id': resource.id,
                        'name': resource.name,
                        'service': service_type,
                        'provider': provider,
                        'location': resource.location,
                        'subscription_id': subscription_id,
                        'tags': [{'Key': k, 'Value': v} for k, v in tags.items()]
                    }
                    
                    # Add project tag in the format expected by the rest of the code
                    resource_info['tags'] = [tag for tag in resource_info['tags'] if tag['Key'].lower() != 'project']
                    resource_info['tags'].append({'Key': 'project', 'Value': project_tag})
                    
                    resources.append(resource_info)
                    logger.info(f"Found resource {resource.name} with project={project_tag} tag")
        
        logger.info(f"Total Azure resources with project tags: {len(resources)}")
        return resources
    
    except Exception as e:
        logger.error(f"Error listing Azure resources: {str(e)}")
        raise

def normalize_application_name(name):
    """Normalize application name for comparison"""
    if not name:
        return ""
    return " ".join(name.split()).strip().lower()

def api_request(method, url, headers, params=None, json_data=None):
    """Centralized API request handler"""
    try:
        if method == 'GET':
            response = requests.get(url, headers=headers, params=params)
        elif method == 'POST':
            response = requests.post(url, headers=headers, params=params, json=json_data)
        elif method == 'DELETE':
            response = requests.delete(url, headers=headers)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")
            
        if response.status_code >= 400:
            logger.error(f"API request failed. Status: {response.status_code}")
            logger.error(f"Response: {response.text}")
            response.raise_for_status()
            
        return response
    except Exception as e:
        logger.error(f"API request error: {str(e)}")
        raise

def get_existing_it_component(service_name, headers):
    """Check if IT Component already exists"""
    display_name = f"AZURE-{service_name.upper()}"
    search_url = f"{LEANIX_API_BASE_URL}/services/pathfinder/v1/factSheets"
    
    params = {
        'type': 'ITComponent',
        'pageSize': 100,
        'filter': f'name="{display_name}"'
    }
    
    logger.info(f"Checking for existing IT Component: {display_name}")
    
    try:
        response = api_request('GET', search_url, headers, params)
        result = response.json()
        
        for fact_sheet in result.get('data', []):
            if fact_sheet.get('name') == display_name:
                logger.info(f"Found existing IT Component with ID: {fact_sheet['id']}")
                return {
                    'id': fact_sheet['id'],
                    'name': fact_sheet['name'],
                    'type': 'ITComponent',
                    'status': fact_sheet.get('status', 'ACTIVE')
                }
        
        logger.info(f"No existing IT Component found for: {display_name}")
        return None
    except Exception as e:
        logger.error(f"Error checking for existing IT Component: {str(e)}")
        return None

def create_it_component_factsheet(resource, headers):
    """Create the IT Component fact sheet"""
    display_name = f"AZURE-{resource['service'].upper()}"
    logger.info(f"Creating fact sheet for {display_name}")
    
    # Double-check for existing component before creation
    existing = get_existing_it_component(resource['service'], headers)
    if existing:
        return existing
    
    current_date = get_current_date()
    
    payload = {
        "name": display_name,
        "description": f"Azure {resource['service']} resource",
        "type": "ITComponent",
        "status": "ACTIVE",
        "fields": [{
            "name": "lifecycle",
            "data": {
                "type": "Lifecycle",
                "phases": [{
                    "phase": "ACTIVE",
                    "startDate": current_date
                }]
            }
        }]
    }
    
    try:
        create_url = f"{LEANIX_API_BASE_URL}/services/pathfinder/v1/factSheets"
        response = api_request('POST', create_url, headers, json_data=payload)
        
        result = response.json()
        fact_sheet_id = result.get('id') or result.get('data', {}).get('id')
        
        if not fact_sheet_id:
            raise Exception("No ID received for created IT Component")
        
        logger.info(f"IT Component created successfully with ID: {fact_sheet_id}")
        
        return {
            'id': fact_sheet_id,
            'name': display_name,
            'type': 'ITComponent',
            'status': 'ACTIVE'
        }
    except Exception as e:
        logger.error(f"Error creating IT Component: {str(e)}")
        raise

def get_application_id(app_name, headers):
    """Get Application Fact Sheet ID by name"""
    search_url = f"{LEANIX_API_BASE_URL}/services/pathfinder/v1/factSheets"
    
    # URL encode the application name for the filter parameter
    encoded_name = urllib.parse.quote(app_name)
    normalized_name = normalize_application_name(app_name)
    
    params = {
        'type': 'Application',
        'pageSize': 100,
        'filter': f'name="{encoded_name}"'
    }
    
    logger.info(f"Searching for application with name: {app_name}")
    
    try:
        response = api_request('GET', search_url, headers, params)
        result = response.json()
        
        # Try exact match first
        for fact_sheet in result.get('data', []):
            if normalize_application_name(fact_sheet.get('name')) == normalized_name:
                logger.info(f"Found exact matching Application: {fact_sheet['name']} with ID: {fact_sheet['id']}")
                return fact_sheet['id']
        
        # If no exact match found, try broader search
        alternative_params = {
            'type': 'Application',
            'pageSize': 100,
            'query': app_name
        }
        
        logger.info(f"No exact match found, trying alternative search for: {app_name}")
        alt_response = api_request('GET', search_url, headers, alternative_params)
        alt_result = alt_response.json()
        
        # Check normalized names
        for fact_sheet in alt_result.get('data', []):
            if normalize_application_name(fact_sheet.get('name')) == normalized_name:
                logger.info(f"Found matching Application using alternative search: {fact_sheet['name']} with ID: {fact_sheet['id']}")
                return fact_sheet['id']
        
        # Log available applications if no match found
        available_apps = [fs.get('name') for fs in result.get('data', [])]
        logger.error(f"No matching Application found for name: {app_name}")
        logger.error(f"Available applications: {available_apps}")
        raise Exception(f"Application not found: {app_name}")
    except Exception as e:
        logger.error(f"Error getting application ID: {str(e)}")
        raise

def check_existing_relation(it_component_id, app_id, headers):
    """Check if relation already exists"""
    relations_url = f"{LEANIX_API_BASE_URL}/services/pathfinder/v1/factSheets/{it_component_id}/relations"
    
    try:
        response = api_request('GET', relations_url, headers)
        relations = response.json()
        
        for relation in relations.get('data', []):
            if relation.get('toId') == app_id:
                logger.info(f"Found existing relation between {it_component_id} and {app_id}")
                return relation
                
        return None
    except Exception as e:
        logger.error(f"Error checking existing relation: {str(e)}")
        return None

def create_relation(it_component_id, app_id, headers):
    """Create relation if it doesn't exist"""
    existing_relation = check_existing_relation(it_component_id, app_id, headers)
    if existing_relation:
        logger.info("Using existing relation")
        return existing_relation
    
    current_date = get_current_date()
    
    payload = {
        "fromId": it_component_id,
        "toId": app_id,
        "type": "relITComponentToApplication",
        "typeFromFS": "ITComponent",
        "typeToFS": "Application",
        "status": "ACTIVE",
        "activeFrom": current_date,
    }
    
    relation_url = f"{LEANIX_API_BASE_URL}/services/pathfinder/v1/factSheets/{it_component_id}/relations"
    
    try:
        response = api_request('POST', relation_url, headers, json_data=payload)
        logger.info(f"Created new relation between {it_component_id} and {app_id}")
        return response.json()
    except Exception as e:
        logger.error(f"Error in create_relation: {str(e)}")
        raise

def map_resources_by_app_and_service(current_resources):
    """Create a mapping of applications to their Azure services"""
    app_service_map = {}
    
    for resource in current_resources:
        project_tag = next((tag['Value'] for tag in resource.get('tags', []) 
                          if tag['Key'].lower() == 'project' and tag['Value'] in PROJECT_APP_MAPPING), None)
        if project_tag:
            app_name = PROJECT_APP_MAPPING[project_tag]
            service_name = resource['service'].lower()
            
            if app_name not in app_service_map:
                app_service_map[app_name] = set()
            
            app_service_map[app_name].add(service_name)
    
    return app_service_map

def get_factsheet_by_id(factsheet_id, headers):
    """Generic function to get any factsheet by ID"""
    url = f"{LEANIX_API_BASE_URL}/services/pathfinder/v1/factSheets/{factsheet_id}"
    
    try:
        response = api_request('GET', url, headers)
        return response.json().get('data', {})
    except Exception as e:
        logger.error(f"Error getting factsheet details: {str(e)}")
        return {}

def delete_relation(app_id, relation_id, headers):
    """Delete a specific relation"""
    delete_url = f"{LEANIX_API_BASE_URL}/services/pathfinder/v1/factSheets/{app_id}/relations/{relation_id}"
    
    try:
        api_request('DELETE', delete_url, headers)
        logger.info(f"Successfully deleted relation {relation_id} from application {app_id}")
        return True
    except Exception as e:
        logger.error(f"Error deleting relation: {str(e)}")
        return False

def cleanup_it_component_relations(it_component_id, current_resources, headers):
    """Clean up relations for an IT Component based on current Azure resources"""
    logger.info(f"Starting cleanup for IT Component {it_component_id}")
    
    try:
        it_component = get_factsheet_by_id(it_component_id, headers)
        it_component_name = it_component.get('name', '')
        
        # Extract service name from IT Component name (e.g., "AZURE-VIRTUALMACHINES" -> "virtualmachines")
        if not it_component_name.startswith('AZURE-'):
            logger.error(f"Invalid IT Component name format: {it_component_name}")
            return []
            
        service_name = it_component_name[6:].lower()
        logger.info(f"Processing cleanup for service: {service_name}")
        
        # Get all current relations for the IT Component
        relations_url = f"{LEANIX_API_BASE_URL}/services/pathfinder/v1/factSheets/{it_component_id}/relations"
        response = api_request('GET', relations_url, headers)
        existing_relations = response.json().get('data', [])
        
        if not existing_relations:
            logger.info("No existing relations found to clean up")
            return []
        
        # Create mapping of applications to their current Azure services
        app_service_map = map_resources_by_app_and_service(current_resources)
        deleted_relations = []
        
        # Check each relation
        for relation in existing_relations:
            app_id = relation.get('toId')
            if not app_id:
                continue
            
            app_details = get_factsheet_by_id(app_id, headers)
            app_name = app_details.get('name')
            if not app_name:
                continue
            
            logger.info(f"Checking application {app_name} for service {service_name}")
            
            # Check if application still has resources of this service type
            if app_name not in app_service_map or service_name not in app_service_map[app_name]:
                logger.info(f"Application {app_name} no longer has {service_name} resources, deleting relation {relation['id']}")
                
                if delete_relation(app_id, relation['id'], headers):
                    deleted_relations.append({
                        'relation_id': relation['id'],
                        'it_component_name': it_component_name,
                        'service': service_name,
                        'application_id': app_id,
                        'application_name': app_name,
                        'timestamp': get_current_timestamp(),
                        'user': get_current_user()
                    })
            else:
                logger.info(f"Application {app_name} still has {service_name} resources, keeping relation {relation['id']}")
        
        return deleted_relations
    except Exception as e:
        logger.error(f"Error in cleanup_it_component_relations: {str(e)}")
        return []

def process_it_component(resource, token, all_resources=None):
    """Process IT Component creation or update with relations"""
    logger.info(f"Processing resource: {resource.get('name', 'unnamed')} ({resource['service']})")
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    try:
        # Get project tag from resource
        project_tag = next(
            (tag['Value'] for tag in resource.get('tags', [])
            if tag['Key'].lower() == 'project' and tag['Value'] in PROJECT_APP_MAPPING),
            None
        )
        
        if not project_tag:
            logger.info(f"No matching project tag found for resource: {resource.get('name', 'unnamed')}")
            return None
        
        # Get or create IT Component
        existing_component = get_existing_it_component(resource['service'], headers)
        
        if existing_component:
            it_component = existing_component
            logger.info(f"Using existing IT Component: {it_component['id']} for service {resource['service']}")
        else:
            it_component = create_it_component_factsheet(resource, headers)
            logger.info(f"Created new IT Component: {it_component['id']} for service {resource['service']}")
        
        # Process current relation
        relations = []
        app_name = PROJECT_APP_MAPPING[project_tag]
        
        try:
            app_id = get_application_id(app_name, headers)
            logger.info(f"Found Application ID {app_id} for {app_name}")
            
            # Check if relation already exists
            existing_relation = check_existing_relation(it_component['id'], app_id, headers)
            
            if existing_relation:
                logger.info(f"Found existing relation between {it_component['id']} and {app_name}")
                relation = existing_relation
            else:
                logger.info(f"Creating new relation between {it_component['id']} and {app_name}")
                relation = create_relation(it_component['id'], app_id, headers)
            
            relations.append({
                'project': project_tag,
                'application': app_name,
                'relation': relation,
                'status': 'existing' if existing_relation else 'new'
            })
        except Exception as e:
            logger.error(f"Failed to process relation for project {project_tag}: {str(e)}")
            relations.append({
                'project': project_tag,
                'application': app_name,
                'error': str(e)
            })
        
        # Clean up old relations if we have all resources
        deleted_relations = []
        if all_resources is not None and existing_component:
            deleted_relations = cleanup_it_component_relations(
                it_component['id'],
                all_resources,
                headers
            )
        
        return {
            'it_component': it_component,
            'relations': relations,
            'deleted_relations': deleted_relations,
            'timestamp': get_current_timestamp(),
            'user': get_current_user()
        }
    except Exception as e:
        logger.error(f"Error in process_it_component: {str(e)}")
        raise

def main():
    """Main execution function"""
    try:
        # Get Azure resources
        resources = list_azure_resources()
        
        # Get LeanIX token
        token = get_leanix_token()
        
        # Process each resource
        results = []
        for resource in resources:
            try:
                result = process_it_component(resource, token, resources)
                if result:
                    results.append(result)
            except Exception as e:
                results.append({
                    'resource': resource,
                    'error': str(e)
                })
        
        final_result = {
            'statusCode': 200,
            'body': {
                'azure_resources': len(resources),
                'leanix_results': results,
                'metadata': {
                    'timestamp': get_current_timestamp(),
                    'user': get_current_user()
                }
            }
        }
        
        # Print summary
        print(f"\nExecution complete. Status code: {final_result['statusCode']}")
        print(f"Total Azure resources found: {final_result['body']['azure_resources']}")
        print(f"Resources processed: {len(results)}")
        
        # Save results to file
        with open('leanix_azure_integration_results.json', 'w') as f:
            json.dump(final_result['body'], f, indent=2)
        print("Results saved to leanix_azure_integration_results.json")
        
        return final_result
    except Exception as e:
        error_result = {
            'statusCode': 500,
            'body': {
                'error': str(e),
                'metadata': {
                    'timestamp': get_current_timestamp(),
                    'user': get_current_user()
                }
            }
        }
        
        print(f"Execution failed: {str(e)}")
        
        # Save error to file
        with open('leanix_azure_integration_error.json', 'w') as f:
            json.dump(error_result['body'], f, indent=2)
        print("Error details saved to leanix_azure_integration_error.json")
        
        return error_result

# Main execution for direct running
if __name__ == "__main__":
    main()