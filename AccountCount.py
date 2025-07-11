import requests
import csv
import time
from collections import Counter # Used for counting accounts by type

# --- Configuration ---
PRISMA_CLOUD_API_URL = "https://api.prismacloud.io"
ACCESS_KEY = "YOUR_ACCESS_KEY_ID"  # Replace with your Access Key ID
SECRET_KEY = "YOUR_SECRET_KEY"    # Replace with your Secret Key

TOKEN = ""
# Delay between API calls to be considerate to the API endpoint
API_CALL_DELAY = 0.5 # Adjust as needed

# --- Function to handle API Login ---
def login_to_prisma_cloud():
    """Logs into Prisma Cloud and stores the auth token globally."""
    global TOKEN
    payload = {"username": ACCESS_KEY, "password": SECRET_KEY}
    headers = {"Content-Type": "application/json", "Accept": "application/json; charset=UTF-8"}
    login_url = f"{PRISMA_CLOUD_API_URL}/login"
    print(f"Attempting login to: {login_url}...")
    try:
        response = requests.post(login_url, headers=headers, json=payload, timeout=30)
        response.raise_for_status() # Raises an HTTPError for bad responses (4XX or 5XX)
        TOKEN = response.json().get("token")
        if TOKEN:
            print("Login successful.")
            return True
        else:
            print("Login successful, but no token was received.")
            return False
    except requests.exceptions.HTTPError as errh:
        print(f"Http Error during login: {errh}")
        response_text = errh.response.text if errh.response else "No response body"
        print(f"Response body: {response_text}")
    except requests.exceptions.RequestException as err:
        print(f"An error occurred during login: {err}")
    return False

# --- Function to Recursively List All Cloud Accounts ---
def list_all_accounts_recursively():
    """
    Lists all cloud accounts, including those nested within organizations.
    Returns a list of dictionaries, each representing a discovered account.
    """
    if not TOKEN:
        print("Authentication token not found. Please login first.")
        return []
        
    headers = {"x-redlock-auth": TOKEN, "Accept": "application/json; charset=UTF-8"}
    list_accounts_url = f"{PRISMA_CLOUD_API_URL}/cloud"
    print(f"\nFetching top-level cloud accounts from: {list_accounts_url}...")
    
    final_account_list = []
    
    try:
        response = requests.get(list_accounts_url, headers=headers, timeout=60)
        response.raise_for_status()
        top_level_accounts = response.json()
        print(f"Found {len(top_level_accounts)} top-level account entries.")

        for account in top_level_accounts:
            account_id = account.get("accountId")
            account_name = account.get("name")
            cloud_type = account.get("cloudType")
            account_type = account.get("accountType") # e.g., ACCOUNT, ORGANIZATION

            # Check if the account is an organization/tenant that may have children
            # For AWS/GCP this is often 'ORGANIZATION', for Azure it might be 'TENANT'
            is_organization = account_type in ["ORGANIZATION", "MASTER_SERVICE_ACCOUNT", "TENANT"]

            if is_organization:
                print(f"  Found Organization Account: '{account_name}'. Discovering member accounts...")
                # Add the parent organization itself to the list for completeness.
                final_account_list.append({
                    "AccountID": account_id,
                    "AccountName": account_name,
                    "CloudType": cloud_type,
                    "ParentAccountName": "N/A (Is Parent)"
                })

                # Endpoint to get member accounts of an organization
                member_accounts_url = f"{PRISMA_CLOUD_API_URL}/cloud/{cloud_type}/{account_id}/project"
                try:
                    time.sleep(API_CALL_DELAY) # Delay before the next API call
                    members_response = requests.get(member_accounts_url, headers=headers, timeout=120)
                    members_response.raise_for_status()
                    member_accounts = members_response.json()
                    print(f"    -> Discovered {len(member_accounts)} member accounts in '{account_name}'.")

                    for member in member_accounts:
                        final_account_list.append({
                            "AccountID": member.get("accountId"),
                            "AccountName": member.get("name"),
                            "CloudType": member.get("cloudType"),
                            "ParentAccountName": account_name # Add parent name for context
                        })
                except requests.exceptions.HTTPError as errh:
                    print(f"    -> Http Error discovering members for '{account_name}': {errh}")
                    # Add an error entry for the failed discovery
                    final_account_list.append({
                        "AccountID": "ERROR", "AccountName": f"Failed to list members for '{account_name}'",
                        "CloudType": cloud_type, "ParentAccountName": account_name
                    })
                except Exception as e:
                    print(f"    -> An unexpected error discovering members for '{account_name}': {e}")

            else: # This is a standard, non-organizational account
                print(f"  Found Standard Account: '{account_name}'.")
                final_account_list.append({
                    "AccountID": account_id,
                    "AccountName": account_name,
                    "CloudType": cloud_type,
                    "ParentAccountName": "N/A (Directly Onboarded)"
                })

    except requests.exceptions.HTTPError as errh:
        print(f"Http Error listing top-level accounts: {errh}")
    except Exception as e:
        print(f"An error occurred while listing accounts: {e}")
        
    return final_account_list

# --- Main Script Execution ---
def main():
    """Main function to orchestrate the script."""
    # Configuration Check
    if PRISMA_CLOUD_API_URL == "https://api.your-region.prismacloud.io" or \
       ACCESS_KEY == "YOUR_ACCESS_KEY_ID" or \
       SECRET_KEY == "YOUR_SECRET_KEY":
        print("ERROR: Please update PRISMA_CLOUD_API_URL, ACCESS_KEY, and SECRET_KEY with your actual details at the top of the script.")
        return

    if login_to_prisma_cloud():
        all_accounts = list_all_accounts_recursively()
        
        if not all_accounts:
            print("No accounts were discovered. Exiting.")
            return

        # --- 1. Calculate Total Count ---
        total_count = len(all_accounts)
        
        # --- 2. Calculate Count by Cloud Type ---
        cloud_types = [acc.get("CloudType", "Unknown") for acc in all_accounts]
        count_by_type = Counter(cloud_types)
        
        # --- 3. Generate CSV Output ---
        output_filename = "prisma_cloud_account_inventory.csv"
        print(f"\n--- Writing Account Inventory Report to {output_filename} ---")
        
        try:
            with open(output_filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)

                # Write summary sections
                writer.writerow(["Total Account Count"])
                writer.writerow([total_count])
                writer.writerow([]) # Blank line separator

                writer.writerow(["Account Count by Cloud Type"])
                writer.writerow(["Cloud Type", "Count"])
                for cloud_type, count in count_by_type.items():
                    writer.writerow([cloud_type, count])
                writer.writerow([]) # Blank line separator

                # Write the full list of accounts
                writer.writerow(["Full Account List"])
                # Define the header for the detailed list
                detailed_header = ["AccountID", "AccountName", "CloudType", "ParentAccountName"]
                writer.writerow(detailed_header)
                
                # Write the account data
                for account in all_accounts:
                    writer.writerow([
                        account.get("AccountID"),
                        account.get("AccountName"),
                        account.get("CloudType"),
                        account.get("ParentAccountName")
                    ])
            
            print(f"Report successfully written to {output_filename}")
            print(f"Summary: Total Accounts = {total_count}, Breakdown by Type = {dict(count_by_type)}")

        except IOError as e:
            print(f"IOError writing report to {output_filename}. Check permissions or path. Error: {e}")
        except Exception as e:
            print(f"An unexpected error occurred while writing the CSV file: {e}")

if __name__ == "__main__":
    main()
