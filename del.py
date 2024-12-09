from pymongo import MongoClient

# Configuration
MONGODB_URI = 'mongodb://localhost:27017'  # MongoDB URI
DATABASE_NAME = 'dashboard'  # Replace with your database name
COLLECTION_NAME = 'ibm_repos'  # Replace with your collection name

# Initialize MongoDB client
client = MongoClient(MONGODB_URI)
db = client[DATABASE_NAME]
collection = db[COLLECTION_NAME]

# Get all documents in the collection
documents = list(collection.find())

# Define the starting index for deletion
start_index = 2860

# Delete documents from the start index to the end
if start_index < len(documents):
    # Create a list of ids to delete
    ids_to_delete = [doc['_id'] for doc in documents[start_index:]]

    # Perform the deletion
    result = collection.delete_many({'_id': {'$in': ids_to_delete}})
    print(f'Deleted {result.deleted_count} documents from the collection.')
else:
    print('Start index is out of range.')

# Close MongoDB connection
client.close()
