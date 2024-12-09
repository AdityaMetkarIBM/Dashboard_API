import os
import requests
import pandas as pd
from dotenv import load_dotenv
from pymongo import MongoClient
from flask import Flask, render_template, request, redirect, url_for, jsonify
from datetime import datetime,timedelta
import json

# Load GitHub token from environment variable
load_dotenv()
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN2')
MONGO_URI = os.getenv('MONGO_URI')



# Base URL and headers for GitHub API requests
BASE_URL = "https://api.github.com"
HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28"
}
github_events = {
    "IssuesEvent",
    "PullRequestEvent",
    "PullRequestReviewEvent",
    "PushEvent"
}



# MongoDB connection
client = MongoClient(MONGO_URI)  
db = client['dashboard']  
user_collection = None # will be set dynamically through routes
data_collection = None


# FLASK APP ---------------------
app = Flask(__name__)


# DATE FUNCTION ------------>

def get_start_date():

    today = datetime.today()
    one_year_back = today - timedelta(days=365)

    return one_year_back

# USER BASE FUNCTIONS ------------------------------->

def get_login_name(username):

    url = f"https://api.github.com/search/users?q={username}"
    response = requests.get(url, headers=HEADERS)  

    if response.status_code == 200:
        search_results = response.json()
        if search_results['total_count'] > 0:
            return search_results['items'][0]['login']
        else:
            return None
    else:
        print(f"Error fetching user by email: {response.status_code} {response.text}")
        return None  # Handle error response appropriately

def get_user_info(username):
    url = f"{BASE_URL}/users/{username}"
    response = requests.get(url, headers=HEADERS)

    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error fetching user info: {response.status_code} {response.text}")
        return {}

def get_user_contributions(username):
    # Corrected GraphQL query
    query = '''
    query($userName: String!) { 
        user(login: $userName){
            contributionsCollection {
                contributionCalendar {
                    totalContributions
                    weeks {
                        contributionDays {
                            contributionCount
                            date
                        }
                    }
                }
            }
        }
    }
    '''

    # Set up the request headers and payload
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.graphql+json"
    }
    payload = {
        "query": query,
        "variables": {"userName": username}  # Fix variable to match the query ($userName)
    }

    # Make the request
    response = requests.post('https://api.github.com/graphql', json=payload, headers=headers)

    if response.status_code == 200:
        contributions = response.json()

        # Check if the response contains valid data
        if 'data' in contributions and contributions['data']:
            user_data = contributions['data'].get('user', {})
            if user_data and 'contributionsCollection' in user_data:
                contribution_data = user_data['contributionsCollection']['contributionCalendar']

                total_contributions = contribution_data.get('totalContributions', 0)
                weeks = contribution_data.get('weeks', [])

                # Return the relevant data
                return {
                    "total": total_contributions,
                    "weeks": weeks
                }
            else:
                print("Error: 'contributionsCollection' not found in the response data")
                return None
        else:
            print(f"Error: 'data' field not found or empty in the response. Response: {json.dumps(contributions, indent=2)}")
            return None

    else:
        print(f"Error fetching contributions: {response.status_code} {response.text}")
        return None

def get_user_repositories(username):
    url = f"{BASE_URL}/users/{username}/repos"
    response = requests.get(url, headers=HEADERS)

    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error fetching repositories: {response.status_code} {response.text}")
        return []

def get_repo_topics(repo_full_name):
    url = f"{BASE_URL}/repos/{repo_full_name}/topics"
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code == 200:
        return response.json().get('names', [])
    else:
        print(f"Error fetching topics: {response.status_code} {response.text}")
        return []

def get_commit_details_from_SHA(repo_full_name, sha):

    url = f"{BASE_URL}/repos/{repo_full_name}/commits/{sha}"
    response = requests.get(url, headers=HEADERS)

    if response.status_code == 200:
        commit_data = response.json()

        if commit_data['commit']['message'][:12] == 'Merge branch':
            merged = True
        else:
            merged = False

        return {
            "sha": commit_data["sha"],
            "message": commit_data["commit"]["message"],
            "date": commit_data["commit"]["committer"]["date"],
            "url": commit_data["html_url"],
            "author": commit_data["commit"]["author"]["name"],
            "merged": merged,
            "stats": commit_data["stats"],
            "files": [{"filename": file['filename'], "additions": file['additions'], "deletions": file['deletions']}
                        for file in commit_data['files']]
        }
    else:
        print(f"Error fetching commit details for {sha}: {response.status_code} {response.text}")
        return None

def get_user_global_commits(repo_full_name, username, start_date):

    #testing
    # return []

    commits_with_details = []
    
    # Step 1: Get all branches
    branches_url = f"{BASE_URL}/repos/{repo_full_name}/branches"
    branches_response = requests.get(branches_url, headers=HEADERS)

    if branches_response.status_code == 200:
        branches = branches_response.json()
        
        for branch in branches:
            branch_name = branch['name']
            page = 1
            
            while True:
                # Fetch commits authored by the specified user for each branch
                url = f"{BASE_URL}/repos/{repo_full_name}/commits?author={username}&sha={branch_name}&per_page=100&page={page}&since={start_date}"
                response = requests.get(url, headers=HEADERS)

                if response.status_code == 200:
                    branch_commits = response.json()
                    if not branch_commits:  # No more commits
                        break

                    # Step 2: Get details for each commit directly
                    for commit in branch_commits:
                        sha = commit["sha"]
                        print(branch_name," - ",sha)

                        detailed_commit = get_commit_details_from_SHA(repo_full_name, sha)

                        if detailed_commit:
                            detailed_commit['branch'] = branch_name
                            detailed_commit['merged'] = False            # Only for Global Commits, set as non-merged
                            commits_with_details.append(detailed_commit)

                    page += 1  # Go to the next page
                else:
                    print(f"Error fetching commits for branch {branch_name}: {response.status_code} {response.text}")
                    break
    else:
        print(f"Error fetching branches: {branches_response.status_code} {branches_response.text}")
    
    return commits_with_details

def get_user_issues(repo_full_name, username, start_date):
    #testing
    # return []

    issues_details = []

    page = 1
    while True:
        url = f"{BASE_URL}/repos/{repo_full_name}/issues?page={page}&per_page=100&state=all&since={start_date}"
        response = requests.get(url, headers=HEADERS)

        if response.status_code == 200:
            issues = response.json()
            if not issues:  # No more issues
                break

            for issue in issues:
                # Check if this is a pull request
                if 'pull_request' in issue:
                    pass
                elif (issue['user']['login'] == username) or any(assignee['login'] == username for assignee in issue['assignees']):
                    print(f"Getting | Issue -> {issue['number']}")
                    
                    issue_data = {
                        'title': issue['title'],
                        'number': issue['number'],
                        'created_at': issue['created_at'],
                        'updated_at': issue['updated_at'],
                        'labels': issue['labels'],
                        'state': issue['state'],
                        'type': 'created' if issue['user']['login'] == username else 'assigned'
                    }
                    
                    issues_details.append(issue_data)

            page += 1  # Go to the next page
        else:
            print(f"Error fetching issues: {response.status_code} {response.text}")
            break

    return issues_details

def get_issue_comments(issue_list, username):
    comments = []

    for issue in issue_list:
        repo_full_name = issue['repo_full_name']
        page = 1
        
        while True:
            url = f"{BASE_URL}/repos/{repo_full_name}/issues/{issue['number']}/comments?page={page}&per_page=100"
            response = requests.get(url, headers=HEADERS)

            if response.status_code == 200:
                issue_comments = response.json()
                if not issue_comments:  # No more comments
                    break

                for comment in issue_comments:
                    if comment['user']['login'] == username:
                        comment_info = {
                            'id': comment['id'],
                            'body': comment['body'],
                            'user': comment['user']['login'],
                            'created_at': comment['created_at'],
                            'updated_at': comment['updated_at'],
                            'html_url': comment['html_url']
                        }
                        comments.append(comment_info)

                page += 1  # Go to the next page
            else:
                print(f"Couldn't fetch comments for issue {issue['number']}: {response.status_code} {response.text}")
                break
    
    return comments

# -- GROUP
def get_pr_details_commits_comments(repo_full_name, username, start_date):

    base_url = f"{BASE_URL}/repos/{repo_full_name}"
    pull_details_list = []
    page = 1
    per_page = 100  # Adjust the number of results per page if necessary

    def get_paginated_data(url):
        """Fetch paginated data from a given URL."""
        data = []
        page = 1
        per_page = 100  # Number of results per page

        while True:
            paginated_url = f"{url}?per_page={per_page}&page={page}"
            response = requests.get(paginated_url, headers=HEADERS)
            
            if response.status_code != 200:
                print(f"Error fetching data from {paginated_url}: {response.json()}")
                break

            page_data = response.json()
            if not page_data:  # Break if no more data
                break

            data.extend(page_data)
            page += 1

        return data
        
    def get_pr_commits(pr_number, username):
        detailed_commits = []

        commits_url = f"{BASE_URL}/repos/{repo_full_name}/pulls/{pr_number}/commits"
        commits = get_paginated_data(commits_url)
        
        # Filter commits by username
        filtered = [commit['sha'] for commit in commits if commit['author'] and commit['author']['login'] == username]

        for sha in filtered:
            details = get_commit_details_from_SHA(repo_full_name,sha)

            if details:
                detailed_commits.append(details)
        
        return detailed_commits

    def get_pr_comments(pr_number, username):

        comments_data = []

        review_url = f"{BASE_URL}/repos/{repo_full_name}/pulls/{pr_number}/reviews"
        reviews = get_paginated_data(review_url)

        for review in reviews:
            if review['user']['login'] == username:
                state = review['state']

                if state == 'APPROVED' or review['body']:
                    data = {
                        'state': "approved",
                        'url': review['html_url'],
                        'comment': review['body'] if review['body'] else None,
                        'date': review['submitted_at'],
                    }
                    comments_data.append(data)

                elif state in ('CHANGES_REQUESTED', 'COMMENTED'):
                    comment_url = review_url + f"/{review['id']}/comments"
                    comments = get_paginated_data(comment_url)

                    for comment in comments:
                        if comment['user']['login'] == username:

                            data = {
                                'state': state.lower(),
                                'url': comment['html_url'],
                                'comment': comment.get('body'),
                                'date': comment['updated_at'],
                                'file': comment.get('path')
                            }
                            comments_data.append(data)

        return comments_data
        
    # ------------------------------


    while True:
        # Step 1: Get all pull requests with pagination
        pulls_url = f"{base_url}/pulls?state=all&per_page={per_page}&page={page}"
        response = requests.get(pulls_url, headers=HEADERS)
        
        if response.status_code != 200:
            print(f"Error fetching pull requests: {response.json()}")
            break

        pull_requests = response.json()

        # Break the loop if no more pull requests are returned
        if not pull_requests:
            break

        # Step 2: Process each pull request
        for pr in pull_requests:
            pr_author = pr['user']['login']
            assigned_by = pr['assignee']['login'] if pr.get('assignee') else None
            assigned_to = [user['login'] for user in pr.get('assignees', [])]
            pr_date = datetime.strptime(pr['created_at'], "%Y-%m-%dT%H:%M:%SZ")

            requested_reviewers = [reviewer['login'] for reviewer in pr.get('requested_reviewers', [])]

            #To HANDLE - If someone approves review, they are removed from requested_reviewers
            try:
                review_url = f"{base_url}/pulls/{pr['number']}/reviews?per_page={per_page}"
                response = requests.get(review_url, headers=HEADERS).json()
                requested_reviewers += list(set(user['user']['login'] for user in response))
            except:
                pass

            # Check Date boundary
            if pr_date<start_date:
                return pull_details_list

            # Check if the author or requested reviewers match the username
            if pr_author == username or (username in requested_reviewers) or (username in assigned_to) or username==assigned_by:
                pr_number = pr['number']
                
                # Get pull request details
                pr_details = get_pr_details(repo_full_name, pr_number)
                if not pr_details:
                    continue
                
                # Get filtered commits
                print(f"Getting --> {pr_number}")
                filtered_commits = get_pr_commits(pr_number, username)
                print("Commits")
                
                # Get filtered review comments
                filtered_comments = get_pr_comments(pr_number, username)
                print("Comments")
                
                # Collect details
                pull_details_list.append({
                    "pr_number": pr_number,
                    "pr_details": pr_details,
                    "commits": filtered_commits,
                    "comments": filtered_comments,
                })

        # Increment the page number for the next request
        page += 1

    return pull_details_list

def get_pr_details(repo_full_name, pr_number):

        url = f"{BASE_URL}/repos/{repo_full_name}/pulls/{pr_number}"
        response = requests.get(url, headers=HEADERS)
        
        if response.status_code == 200:
            data = response.json()

            pr_details = {
                "title": data["title"],
                "number": data["number"],
                "state": data["state"],
                "merged": data["merged"],
                "url": data["html_url"],
                "date": data['created_at'],
                "requested_reviewers": [reviewer["login"] for reviewer in data["requested_reviewers"]],
                "assigned_by": data['assignee']['login'] if data.get('assignee') else None,
                "assigned_to": [user['login'] for user in data.get('assignees', [])],
                "labels": [label["name"] for label in data["labels"]],
                "comments": data["comments"],
                "review_comments": data["review_comments"],
                "commits": data["commits"],
                "additions": data["additions"],
                "deletions": data["deletions"],
                "changed_files": data["changed_files"]
        }

            return pr_details
        else:
            print(f"Error fetching PR details for #{pr_number}: {response.json()}")
            return None
# --


# UPDATE FUNCTIONS ------------------------------>

def update_repo_details(username, repo_details, start_date):

    page = 1
    checkpoint_reached = False  # Last Saved Snapshot
    valid_date = True           # Window till start_date
    latest_snapshot_id = -1   # Initialize latest_snapshot_id to track the latest event ID

    new_updates = {
        'commits': [],
        'new_issues': [],
        'new_prs': []
    }

    while (not checkpoint_reached) and valid_date:
        event_url = f"{BASE_URL}/users/{username}/events?per_page=100&page={page}"
        response = requests.get(event_url, headers=HEADERS)
        
        if response.status_code == 200:
            data = response.json()

            # If no more events are returned, break the loop
            if not data:
                break

            # Check Valid Events
            for event in data:
                if page!=1:    # Perform below code only for the first page time 
                    break

                if (event['type'] in github_events) and (repo_details['name'] in event['repo']['name']):
                    
                    # No new data
                    if repo_details['snapshot'] == event['id']:
                        print("Repo is Up to Date")
                        return repo_details
                    else:
                        # Set new snapshot
                        latest_snapshot_id = event['id']
                        break

            # Update Data -------------------
            print("Updating Data -->")

            for event in data:
                event_date = datetime.strptime(event['created_at'], "%Y-%m-%dT%H:%M:%SZ")

                # Invalid Event
                if (event['type'] not in github_events) or (repo_details['name'] not in event['repo']['name']):
                    print("Invalid -- ", event['type'])
                    continue
                
                # Update till we reach Snapshot
                if repo_details['snapshot'] == event['id']:
                    print("Checkpoint Reached <->", event['id'])
                    checkpoint_reached = True
                    break
                
                # Don't go beyond start date limit
                if event_date<start_date:
                    valid_date = False
                    break

                match event['type']:
                    case 'IssuesEvent':
                        new, (issue_no, data) = handle_issue_event(event, username)
                        print(f"issue Update -- {issue_no}")

                        if new:
                            new_updates['new_issues'] += [data]

                        else:
                            # Assign the latest data
                            if issue_no and issue_no not in new_updates:
                                new_updates[issue_no] = data

                    case 'PullRequestEvent':
                        new, data = handle_pull_request_event(event, repo_details, username)

                        if new:
                            new_updates['new_prs'] += [data]
                        
                        else:
                            pr_no, data = data

                            if pr_no not in new_updates:
                                new_updates[pr_no] = {'pr_details': None, 'commits': [], 'comments': []}

                            new_updates[pr_no]['pr_details'] = data

                    case 'PullRequestReviewEvent':
                        pr_no,comments = handle_pull_request_review_event(event, username)
                        pr_details = get_pr_details(event['repo']['name'], event['payload']['pull_request']['number'])

                        if pr_no not in new_updates:
                            new_updates[pr_no] = {'pr_details': None, 'commits': [], 'comments': []}
                        
                        new_updates[pr_no]['comments'] += comments

                        if pr_details:
                            new_updates[pr_no]['pr_details'] = pr_details

                    case 'PushEvent':
                        commit_data, isGlobal = handle_push_event(event, repo_details)

                        if isGlobal:
                            new_updates['commits'] += [commit_data]
                            print("Global Commit")
                        else:
                            (pr_no, pr_commit) = commit_data
                            if not pr_no:
                                continue
                            if pr_no not in new_updates:
                                new_updates[pr_no] = {'pr_details': None, 'commits': [], 'comments': []}

                            # This is to handle cases when forks are updated in PushEvent (not required)
                            if pr_commit['author'] == username:
                                new_updates[pr_no]['commits'] += [pr_commit]
                                print("PR Commit", pr_no)

                                pr_details = get_pr_details(repo_details['full_name'], pr_no)
                                if pr_details:
                                    new_updates[pr_no]['pr_details'] = pr_details

                    case _:
                        print(f"Unwanted Event -- {event['type']}")

            # Increment the page number for the next request
            page += 1

        else:
            print(f"Failed to fetch events for {username}, Status Code: {response.status_code}")
            return repo_details  # Exit if the request fails

    # If checkpoint not found -- 90 days gap  
    if not checkpoint_reached:
        return 'redirect'

    # ---> Update database repo_details with the <new_updates> dict

    repo_details['commits'] += new_updates['commits']
    repo_details['pull_requests'] += new_updates['new_prs']
    repo_details['issues'] += new_updates['new_issues']

    del new_updates['commits']
    del new_updates['new_prs']
    del new_updates['new_issues']

    # Update issues
    for idx,issue in enumerate(repo_details['issues']):
        if issue['number'] in new_updates:
            repo_details['issues'][idx] = new_updates[issue['number']]
            del new_updates[issue['number']]
    
    # Update PRs
    for idx,pr in enumerate(repo_details['pull_requests']):
        if pr['pr_number'] in new_updates:
            
            pr_changes = new_updates[pr['pr_number']]

            # If new detail changes
            if pr_changes['pr_details']:
                repo_details['pull_requests'][idx]['pr_details'] = pr_changes['pr_details']
            
            if pr_changes['commits']:
                repo_details['pull_requests'][idx]['commits'] += pr_changes['commits']
            
            if pr_changes['comments']:
                repo_details['pull_requests'][idx]['comments'] += pr_changes['comments']
        
            del new_updates[pr['pr_number']]

    # If anything remains, it is a new pull request with comments --> So append it directly
    for pr_no in new_updates:
        new_updates[pr_no]['pr_number'] = pr_no
        repo_details['pull_requests'].append(new_updates[pr_no].copy())
        

    # Set Latest Snapshot
    repo_details['snapshot'] = latest_snapshot_id

    return repo_details


def handle_issue_event(event, username):

    issue = event['payload']['issue']        

    issue_data = {
        'title': issue['title'],
        'number': issue['number'],
        'created_at': issue['created_at'],
        'updated_at': issue['updated_at'],
        'labels': issue['labels'],
        'state': issue['state'],
        'type': 'created' if issue['user']['login'] == username else 'assigned'
    }

    if event['payload']['action'] == 'opened':
        return True, (issue['number'], issue_data)
    else:
        return False, (issue['number'], issue_data)
    
def handle_pull_request_event(event, repo_detail, username):

    data = event['payload']['pull_request']
    pr_details = {
            "title": data["title"],
            "number": data["number"],
            "state": data["state"],
            "merged": data["merged"],
            "url": data["html_url"],
            "date": data['created_at'],
            "requested_reviewers": [reviewer["login"] for reviewer in data["requested_reviewers"]],
            "assigned_by": data['assignee']['login'] if data.get('assignee') else None,
            "assigned_to": [user['login'] for user in data.get('assignees', [])],
            "labels": [label["name"] for label in data["labels"]],
            "comments": data["comments"],
            "review_comments": data["review_comments"],
            "commits": data["commits"],
            "additions": data["additions"],
            "deletions": data["deletions"],
            "changed_files": data["changed_files"]
        }

    if event['payload']['action'] == 'opened':
        # New pr object
        new_pr = {'pr_number': data['number'],
                  'pr_details': None,
                  'commits': [],
                  'comments': []
                }

        new_pr['pr_details'] = pr_details

        # Fetch Commits
        commits_url = data['commits_url']
        response = requests.get(commits_url, headers=HEADERS)

        if response.status_code == 200:
            fetched_commits = response.json()
        else:
            fetched_commits = []
        
        
        # Filter commits by username
        filtered = [commit['sha'] for commit in fetched_commits if commit['author'] and commit['author']['login'] == username]
        commit_details = []

        for sha in filtered:
            details = get_commit_details_from_SHA(repo_detail['full_name'],sha)

            if details:
                commit_details.append(details)

        new_pr['commits'] = commit_details

        return True, new_pr
        
    else:
        # Return the current PR directly
        return False, (pr_details['number'], pr_details)

def handle_pull_request_review_event(event,username):
    
    comments_data = []
    review = event['payload']['review']
    
    # Review Approved  |OR|  # If event has body -- then it was a single comment and no comments exist further
    if review['state'] == 'approved' or review['body']:
        data = {
            'state': review['state'],
            'url': review['html_url'],
            'comment': review['body'] if review['body'] else None,
            'date': review['submitted_at'],
        }
        comments_data.append(data)

    elif review['state'] in ('changes_requested', 'commented'):

        # Fetch all the comments
        comment_url = review['pull_request_url'] + f"/reviews/{review['id']}/comments"
        response = requests.get(comment_url, headers=HEADERS)

        if response.status_code == 200:
            fetched_comments = response.json()
        else:
            fetched_comments = []


        for comment in fetched_comments:
            if comment['user']['login'] == username:
                data = {
                        'state': review['state'],
                        'url': comment['html_url'],
                        'comment': comment.get('body'),
                        'date': comment['updated_at'],
                        'file': comment.get('path')
                    }
                comments_data.append(data)
    
    return event['payload']['pull_request']['number'],comments_data

def handle_push_event(event, repo_details):

    commit =  event['payload']['commits'][-1]
    commit_sha = commit['sha']


    # Global Commits 
    if repo_details['full_name'] == event['repo']['name']:
        return get_commit_details_from_SHA(repo_details['full_name'], commit_sha), True
    
    # PR Commits
    else:
        
        url = f"{BASE_URL}/repos/{event['repo']['name']}/commits/{commit_sha}/pulls"
        response = requests.get(url, headers=HEADERS)
        
        if response.status_code == 200:
            pulls = response.json()
            # If there are associated pull requests, return the number of the first one
            if pulls:
                pr_no = pulls[0]['number']
            else:
                pr_no = None
        else:
            print(f"Error fetching pull requests: {response.status_code} - {response.text}")
            return (None,None),False

        return (pr_no, get_commit_details_from_SHA(repo_details['full_name'], commit_sha)), False



#Direct Frontend-Backend Mapping Routes -------------->
@app.route('/favicon.ico')
def favicon():
    return '', 204  # No content


@app.route('/<user>', methods=['GET', 'POST'])
def get_user(user):
    login_name = get_login_name(user)
    
    if login_name:
        user_info = get_user_info(login_name)
        
        if user_info:
            return jsonify(user_info)
        else:
            return jsonify({"error": f"Something Went Wrong -- fetching User Data -> {login_name}"}), 500 
    else:
        return jsonify({"error": f"Invalid username or email: {user}"}), 400



@app.route('/<user>/contributions', methods=['GET','POST'])
def get_contributions(user):

    username = user
    user_contributions = get_user_contributions(username)

    if user_contributions:
        return jsonify(user_contributions)
    else:
        return jsonify({"error": f"Something Went Wrong -- fetching Contributions -> {username}"}), 500 



@app.route('/<user>/repos', methods=['GET','POST'])
def get_user_repos(user):

    user_info = get_user_info(get_login_name(user))
    username = user_info['login']

    user_repos = get_user_repositories(username)

    repo_names = [repo['name'] for repo in user_repos]

    if user_repos:
        return jsonify(repo_names)
    else:
        return jsonify({"error": f"Something Went Wrong -- fetching All Repos --> {username}"}), 500 
        




# Mapping Backend -- MongoDB -- Frontend Routes ------------>

@app.route('/<org>/<user>/<repo>/repo_details', methods=['GET', 'POST'])
def get_repo_data_from_db(org, user, repo):

    # Set Collecions Dynamically
    user_collection = db[f"{org}_user_data"]
    data_collection = db[f"{org}_github_data"]

    invalid = False
    start_date = get_start_date()  
    user_info = get_user_info(get_login_name(user))
    username = user_info['login']
    
    # Update the Org Members collection

    user_collection.update_one(
        {"login": username}, 
        {"$set": user_info},
        upsert=True
    )

    # Check if the user exists in the database
    db_user_data = data_collection.find_one({"user_info.login": username})  
    if not db_user_data:
        print("No User")
        invalid = True  
        

    # Check if the repo exists in the user's object
    db_repo_details = db_user_data.get(repo) if db_user_data else None
    if not db_repo_details:
        print("No Repo")
        invalid = True  


    # User or repo does not exist, upsert user info and repo details
    if invalid:

        if not user_info:
            return jsonify({"error": f"User data not found for {user}"}), 404

        user_repos = get_user_repositories(username)

        # Find the requested repo details
        parent_repo = next((base_repo for base_repo in user_repos if base_repo['name'] == repo), None)
        if parent_repo is None:
            return jsonify({"error": f"{repo} Repository does not exist for user {user}."}), 404
        



        # If the repo is a fork, get its parent repo details
        if parent_repo['fork']:
            repo_full_name = parent_repo['full_name']
            parent_url = f"{BASE_URL}/repos/{repo_full_name}"
            parent_response = requests.get(parent_url, headers=HEADERS)

            if parent_response.status_code == 200:
                response = parent_response.json()
                parent_repo = response['parent']

        repo_details = {
            "id": parent_repo["id"],
            "name": parent_repo["name"],
            "full_name": parent_repo["full_name"],
            "description": parent_repo["description"],
            "url": parent_repo["html_url"],
            "created_at": parent_repo["created_at"],
            "updated_at": parent_repo["updated_at"],
            "language": parent_repo["language"],
            "owner": {
                "login": parent_repo["owner"]["login"],
                "avatar_url": parent_repo["owner"]["avatar_url"],
                "url": parent_repo["owner"]["html_url"]
            },
            "stars": parent_repo["stargazers_count"],
            "watchers_count": parent_repo["watchers_count"],
            "forks_count": parent_repo["forks_count"],
            "open_issues_count": parent_repo["open_issues_count"],
            "default_branch": parent_repo["default_branch"],
            "visibility": parent_repo["visibility"],
            "topics": get_repo_topics(parent_repo["full_name"]),
        }

        repo_details['commits'] = get_user_global_commits(parent_repo['full_name'], user_info['login'], start_date)
        repo_details['issues'] = get_user_issues(repo_details['full_name'], user, start_date)
        repo_details['pull_requests'] = get_pr_details_commits_comments(repo_details['full_name'], user, start_date)




        # Set the Snapshot -- For update tracking
        event_url = f"{BASE_URL}/users/{username}/events?per_page=100"
        response = requests.get(event_url, headers=HEADERS)

        # Set Dummy Snapshot -- if No Previous Activity in 90 days / No Valid Event Found
        repo_details['snapshot'] = '-1'
        
        if response.status_code == 200:
            data = response.json()

            for event in data:
                if (event['type'] in github_events) and (repo_details['name'] in event['repo']['name']):
                    latest_event_id = event['id']
                    repo_details['snapshot'] = latest_event_id
                    break

        else:
            print(f"Failed to fetch events for {username}")


        # Upsert the user info and repo details into the database
        data_collection.update_one(
            {"user_info.login": user_info.get('login')}, 
            {"$set": {"user_info": user_info, repo: repo_details}},
            upsert=True
        )

        return jsonify(repo_details), 200  
    




    # If both user and repo exist, update DB and Return Data
    else:

        # Note --- current workaround till we find a way to check latest repo activity
        if db_repo_details['snapshot'] == '-1':
            return jsonify(db_repo_details), 200


        latest_repo_data = update_repo_details(username, db_repo_details, start_date)
        
        # If the snapshot was not found -- 90 days outdated
        if latest_repo_data == 'redirect':
            try:
                data_collection.update_one(
                    {"user_info.login": username},
                    {"$unset": {repo: ""}}  # Remove the repo entirely
                )         
                return redirect(f'/{org}/{username}/{repo}/repo_details') # Call Same route without repo - to update entirely
            except:
                return jsonify({"error":"Redirect Failed"}), 500
            
        try:
            data_collection.update_one(
                {"user_info.login": username}, 
                {"$set": {repo: latest_repo_data}},
                upsert=True
            )
            print("DB Updated Successfully")
        except:
            print("DB Update Failed")

        return jsonify(latest_repo_data), 200


if __name__ == '__main__':
    app.run()
