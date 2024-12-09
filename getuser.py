import requests
from pymongo import MongoClient, UpdateOne
import dotenv
import os
import time

dotenv.load_dotenv()

# Configuration
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')  # GitHub token
ORG_NAME = 'ibm'  # Organization name
MONGODB_URI = 'mongodb://localhost:27017'  # MongoDB URI
DATABASE_NAME = 'dashboard'  # Database name
COLLECTION_NAME = 'IBM_user_data'  # Collection to store organization members
REPOS_COLLECTION_NAME = 'ibm_repos'  # Collection to store repos to avoid duplicate fetch

# Initialize MongoDB client
client = MongoClient(MONGODB_URI)
db = client[DATABASE_NAME]
user_collection = db[COLLECTION_NAME]
repos_collection = db[REPOS_COLLECTION_NAME]

# Function to fetch all organization members
def fetch_org_members():
    print(f"Fetching members for organization: {ORG_NAME}")
    members = []
    page = 1  # Start with the first page

    while True:
        url = f'https://api.github.com/orgs/{ORG_NAME}/members?per_page=100&page={page}'
        headers = {'Authorization': f'token {GITHUB_TOKEN}'}
        
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            if not data:  # If no data, break the loop
                break
            
            members.extend(data)
            print(f"Fetched {len(data)} members from page {page}")
            page += 1  # Increment the page number for the next request
        else:
            print(f"Error fetching members: {response.status_code} {response.text}")
            break

    print(f"Total members fetched: {len(members)}")
    return members

# Function to fetch all repositories of the organization
def fetch_org_repos():
    print(f"Fetching repositories for organization: {ORG_NAME}")
    repos = []
    page = 1

    while True:
        url = f'https://api.github.com/orgs/{ORG_NAME}/repos?per_page=100&page={page}'
        headers = {'Authorization': f'token {GITHUB_TOKEN}'}
        
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            if not data:
                break
            
            repos.extend(data)
            print(f"Fetched {len(data)} repos from page {page}")
            page += 1
        else:
            print(f"Error fetching repos: {response.status_code} {response.text}")
            break

    print(f"Total repositories fetched: {len(repos)}")
    return repos

# Function to fetch user details
def fetch_user_details(username):
    print(f"Fetching details for user: {username}")
    url = f'https://api.github.com/users/{username}'
    headers = {'Authorization': f'token {GITHUB_TOKEN}'}
    
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
            user_details = response.json()
            print(f"Fetched details for user: {username}")
            return user_details
    else:
        print(f"Error fetching user details for {username}: {response.status_code} {response.text}")
        return None


# Save or update a single user in MongoDB
def upsert_member_to_mongo(user_details):
    try:
        user_collection.update_one(
            {'login': user_details['login']},
            {'$set': user_details},
            upsert=True
        )
        print(f'Upserted member: {user_details["login"]} to MongoDB.')
    except Exception as e:
        print(f"Error upserting member {user_details['login']}: {e}")

# Function to fetch contributors of a repository
def fetch_contributors(repo_full_name):
    print(f"Fetching contributors for repo: {repo_full_name}")
    url = f'https://api.github.com/repos/{repo_full_name}/contributors'
    headers = {'Authorization': f'token {GITHUB_TOKEN}'}
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            contributors = response.json()
            print(f"Fetched {len(contributors)} contributors for {repo_full_name}")
            return contributors
        else:
            print(f"Error fetching contributors for {repo_full_name}: {response.status_code} {response.text}")
            return []
    except Exception as e:
        print(f"Error fetching contributors for {repo_full_name}: {e}")
        return []

if __name__ == '__main__':
    # org_members = fetch_org_members()

    # # Upsert organization members
    # for member in org_members:
    #     user_details = fetch_user_details(member['login'])
    #     if user_details:
    #         upsert_member_to_mongo(user_details)

    org_repos = fetch_org_repos()
    repo_names = {repo['full_name'] for repo in org_repos}

    for repo in org_repos:
        repo_full_name = repo['full_name']
        # Check if this repo has already been processed
        if repos_collection.find_one({'full_name': repo_full_name}):
            print(f"Repo {repo_full_name} already processed, skipping...")
            continue

        contributors = fetch_contributors(repo_full_name)
        for contributor in contributors:
            contributor_details = fetch_user_details(contributor['login'])

            if not contributor_details:
                print(f"Failed to fetch details for contributor {contributor['login']}.")
                print(f"Last processed: Repo: {repo_full_name}, Contributor: {contributor['login']}")
                break 
            
            upsert_member_to_mongo(contributor_details)

        # Mark the repo as processed
        try:
            repos_collection.insert_one({'full_name': repo_full_name})
            print(f"Marked repo {repo_full_name} as processed.")
        except Exception as e:
            print(f"Error marking repo {repo_full_name}: {e}")

    # Close MongoDB connection
    client.close()
    print("Finished saving all members and contributors.")
