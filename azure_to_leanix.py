import requests
import subprocess
import json
import base64
import datetime

# Step 1: Scan Azure resources using Azure CLI
def scan_azure_resources():
    # Get all resources
    result = subprocess.run(
        ["az", "resource", "list", "--output", "json"], 
        capture_output=True, 
        text=True,
        check=True
    )
    
    return json.loads(result.stdout)

# Step 2: Process Azure resources for LeanIX
def prepare_leanix_components(resources):
    # Group by resource type
    resource_types = {}
    component_to_apps = {}  # Track which component should be linked to which applications
    
    # Application mapping configuration
    app_mapping = {
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
    
    for resource in resources:
        resource_type = resource["type"]
        if resource_type not in resource_types:
            resource_types[resource_type] = []
        resource_types[resource_type].append(resource)
        
        # Check if resource has tags with project information
        if "tags" in resource and resource["tags"] and "project" in resource["tags"]:
            project_tag = resource["tags"]["project"]
            if project_tag in app_mapping:
                component_name = f"Azure {resource_type.replace('Microsoft.', '')}"
                if component_name not in component_to_apps:
                    component_to_apps[component_name] = set()
                component_to_apps[component_name].add(app_mapping[project_tag])
    
    # Create LeanIX component objects
    components = []
    for resource_type, items in resource_types.items():
        # Clean up name from "Microsoft.ServiceName" to "ServiceName"
        service_name = resource_type.replace("Microsoft.", "")
        component_name = f"Azure {service_name}"
        
        component = {
            "name": component_name,
            "type": "ITComponent",
            "description": f"Azure {service_name} used in our application",
            "lifecycle": {
                "phases": [{"phase": "ACTIVE"}]
            },
            "categories": ["Azure Cloud Service"],
            "applications": list(component_to_apps.get(component_name, set()))  # Store related applications
        }
        components.append(component)
    
    return components, component_to_apps

# Revised function to find IT Component factsheet by exact name
def find_itcomponent_id(component_name, token, base_url):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    try:
        browse_url = f"{base_url}/services/pathfinder/v1/factSheets"
        params = {
            'type': 'ITComponent',
            'pageSize': 100  # Increase to get more results
        }
        
        response = requests.get(browse_url, headers=headers, params=params)
        response.raise_for_status()
        
        data = response.json()
        # Find exact match by name
        for item in data.get('data', []):
            if item.get('name') == component_name:
                return item['id']
        return None
        
    except Exception as e:
        print(f"Error finding IT Component: {str(e)}")
        if hasattr(e, 'response') and hasattr(e.response, 'text'):
            print(f"Response text: {e.response.text}")
        return None

# Revised function to find application factsheet by exact name
def find_application_id(app_name, token, base_url):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    try:
        browse_url = f"{base_url}/services/pathfinder/v1/factSheets"
        params = {
            'type': 'Application',
            'pageSize': 100  # Increase to get more results
        }
        
        response = requests.get(browse_url, headers=headers, params=params)
        response.raise_for_status()
        
        data = response.json()
        # Find exact match by name
        for item in data.get('data', []):
            if item.get('name') == app_name:
                return item['id']
        return None
        
    except Exception as e:
        print(f"Error getting application fact sheet: {str(e)}")
        if hasattr(e, 'response') and hasattr(e.response, 'text'):
            print(f"Response text: {e.response.text}")
        return None

# Check if relation exists between IT Component and Application
def check_existing_relation(it_component_id, app_id, headers, base_url):
    """Check if relation already exists"""
    try:
        relations_url = f"{base_url}/services/pathfinder/v1/factSheets/{it_component_id}/relations"
        response = requests.get(relations_url, headers=headers)
        
        if response.status_code == 200:
            relations = response.json()
            for relation in relations.get('data', []):
                if relation.get('toId') == app_id and relation.get('type') == 'relITComponentToApplication':
                    print(f"Found existing relation between {it_component_id} and {app_id}")
                    return relation
        return None
        
    except Exception as e:
        print(f"Error checking existing relation: {str(e)}")
        return None

# Create relation between IT Component and Application
def create_relation(it_component_id, app_id, headers, base_url):
    """Create relation if it doesn't exist"""
    try:
        # Check for existing relation
        existing_relation = check_existing_relation(it_component_id, app_id, headers, base_url)
        if existing_relation:
            print("Using existing relation")
            return existing_relation
            
        # Get current date in format YYYY-MM-DD
        current_date = datetime.datetime.now().strftime("%Y-%m-%d")
            
        # Create new relation
        payload = {
            "fromId": it_component_id,
            "toId": app_id,
            "type": "relITComponentToApplication",
            "typeFromFS": "ITComponent",
            "typeToFS": "Application",
            "status": "ACTIVE",
            "activeFrom": current_date,
        }
        
        relation_url = f"{base_url}/services/pathfinder/v1/factSheets/{it_component_id}/relations"
        response = requests.post(relation_url, headers=headers, json=payload)
        
        if response.status_code != 200 and response.status_code != 201:
            raise Exception(f"Failed to create relation. Status: {response.status_code}, Response: {response.text}")
            
        print(f"Created new relation between {it_component_id} and {app_id}")
        return response.json()
        
    except Exception as e:
        print(f"Error in create_relation: {str(e)}")
        if hasattr(response, 'text'):
            print(f"Response: {response.text}")
        raise

# Step 3: Create IT Components in LeanIX and establish relations with Applications
def create_leanix_components(components, component_to_apps, api_token, base_url):
    # Step 1: Get Access Token using Basic Auth
    auth_url = f"{base_url}/services/mtm/v1/oauth2/token"
    auth_string = f"apitoken:{api_token}"
    auth_header = base64.b64encode(auth_string.encode()).decode()

    headers = {
        "Authorization": f"Basic {auth_header}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    data = {
        "grant_type": "client_credentials"
    }

    try:
        auth_response = requests.post(auth_url, headers=headers, data=data)
        auth_response.raise_for_status()
        token = auth_response.json().get("access_token")
    except Exception as e:
        print(f"Error getting token: {str(e)}")
        if hasattr(e, "response") and hasattr(e.response, "text"):
            print(f"Auth response: {e.response.text}")
        return

    # Create API headers with token
    api_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Step 2: Get application IDs
    app_ids = {}
    for component in components:
        if "applications" in component:
            for app_name in component["applications"]:
                if app_name not in app_ids:
                    app_id = find_application_id(app_name, token, base_url)
                    if app_id:
                        app_ids[app_name] = app_id
                        print(f"Found Application '{app_name}' with ID: {app_id}")
                    else:
                        print(f"Warning: Application '{app_name}' not found in LeanIX")

    # Step 3: Process each component
    for component in components:
        component_name = component["name"]
        applications = component.pop("applications", []) if "applications" in component else []
        
        # Check if IT Component already exists using the new function
        component_id = find_itcomponent_id(component_name, token, base_url)
        
        # If component doesn't exist, create it
        if not component_id:
            try:
                response = requests.post(
                    f"{base_url}/services/pathfinder/v1/factSheets",
                    headers=api_headers,
                    json=component
                )
                response.raise_for_status()
                component_id = response.json().get("id")
                print(f"Created new IT Component: {component_name} with ID: {component_id}")
            except Exception as e:
                print(f"Error creating IT Component {component_name}: {str(e)}")
                if hasattr(e, "response") and hasattr(e.response, "text"):
                    print(f"Response: {e.response.text}")
                continue
        else:
            print(f"IT Component {component_name} already exists with ID: {component_id}")
        
        # Create relations to applications
        for app_name in applications:
            if app_name in app_ids:
                try:
                    create_relation(component_id, app_ids[app_name], api_headers, base_url)
                except Exception as e:
                    print(f"Failed to create relation for {component_name} to {app_name}: {str(e)}")
            else:
                print(f"Skipping relation for {app_name}: Application ID not found")

# Main execution
if __name__ == "__main__":
    leanix_base_url = "https://vinfast.leanix.net"  # Replace with your LeanIX instance
    leanix_api_token = "xxxxxxx"
    
    resources = scan_azure_resources()
    components, component_to_apps = prepare_leanix_components(resources)
    create_leanix_components(components, component_to_apps, leanix_api_token, leanix_base_url)