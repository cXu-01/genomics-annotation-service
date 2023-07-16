# archive.py
#
# NOTE: This file lives on the Utils instance
#
# Copyright (C) 2011-2019 Vas Vasiliadis
# University of Chicago
##
__author__ = 'Vas Vasiliadis <vas@uchicago.edu>'

import os
import sys
import boto3
import json
# Import utility helpers
sys.path.insert(1, os.path.realpath(os.path.pardir))
import helpers

# Get configuration
from configparser import SafeConfigParser
config = SafeConfigParser(os.environ)
config.read('archive_config.ini')

# Add utility code here

### EOF

AWS_REGION = config.get('aws', 'AwsRegionName')
QUEUE_NAME = config.get('QUEUE', 'queue_name')
ARCHIVE_QUEUE_URL= config.get('QUEUE', 'archive_sqs')
DYNAMODB_TABLE = config.get('DYNAMODB', 'annotations_table')
RESULTS_BUCKET = config.get('S3', 'results_bucket')
VAULT_NAME = config.get('S3', 'vault_name')
accounts_db= config.get('USER', 'accounts_db')

# Create a new SQS client and specify AWS region
sqs = boto3.client('sqs', region_name=AWS_REGION)

# Create a new S3 client
s3 = boto3.client('s3', region_name=AWS_REGION)

# Create a new Glacier client
glacier = boto3.client('glacier', region_name=AWS_REGION)

# Create a new DynamoDB resource
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
table = dynamodb.Table(DYNAMODB_TABLE)




def is_premium_user(user_id):

    user_profile = helpers.get_user_profile(id=user_id, db_name=accounts_db)
    user_type = user_profile[4] 

    return user_type == 'premium_user'



# Archive a file to Glacier
# https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/get_object.html
def archive_to_glacier(bucket, key, vault_name):
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
    except Exception as e:
        print(f"An issue occurred while attempting to retrieve the file from S3: {e}")
        return

    data = response['Body'].read()
    try:
        # Set status to 'pending', initiate archive
        # https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GettingStarted.UpdateItem.html
        try:
            table.update_item(
                Key={
                    'job_id': job_id
                },
                UpdateExpression='SET archive_status = :val1',
                ExpressionAttributeValues={
                    ':val1': "pending"
                }
            )
        except Exception as e:
            print(f"An error occurred while trying to update the item archive pending status in DynamoDB: {e}")
            return
        archive = glacier.upload_archive(vaultName=vault_name, body=data)
    except Exception as e:
        print(f"There was a problem when trying to upload the file to Glacier: {e}")
        return
    archive_id =  archive['archiveId']
    try:
        s3.delete_object(Bucket=RESULTS_BUCKET, Key=s3_key_result_file)
        # https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GettingStarted.UpdateItem.html
        # Update archive_status and archive_id for future file restore once archive completed
        try:
            table.update_item(
                Key={
                    'job_id': job_id
                },
                UpdateExpression='SET results_file_archive_id = :val1, archive_status = :val2',
                ExpressionAttributeValues={
                    ':val1': archive_id,
                    ':val2': "completed"
                }
            )
            print(f"{job_id} upload to glacier and removed from S3 successfully.")
        except Exception as e:
            print(f"An error occurred while trying to update the item archive completed stautus and archive id in DynamoDB: {e}")
            return
    
    except Exception as e:
        print(f"There was an issue when trying to delete the file from S3: {e}")
        return

    
while True:
    #long polling
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/sns.html
    messages = sqs.receive_message(
            QueueUrl=ARCHIVE_QUEUE_URL,
            MaxNumberOfMessages=10, 
            WaitTimeSeconds=5  
        )

    if 'Messages' in messages:
            for message in messages['Messages']:
                try:
                    sns_message = json.loads(message['Body'])
                    message_body = json.loads(sns_message['Message'])
                    job_id = message_body['job_id']
                    response = table.get_item(
                        Key={
                            'job_id': job_id
                        }
                    )
                    user_id = response['Item']['user_id']
                    s3_key_result_file = response['Item']['s3_key_result_file']
                     # Archive the file to Glacier if not premium user
                    if not is_premium_user(user_id):
                        archive_id = archive_to_glacier(RESULTS_BUCKET, s3_key_result_file, VAULT_NAME)
                    sqs.delete_message(
        QueueUrl=ARCHIVE_QUEUE_URL,
        ReceiptHandle=message['ReceiptHandle']
    )
                except Exception as e:
                    print("error:",e)

