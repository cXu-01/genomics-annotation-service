# restore.py
#
# NOTE: This file lives on the Utils instance
#
# Copyright (C) 2011-2019 Vas Vasiliadis
# University of Chicago
##
__author__ = 'Vas Vasiliadis <vas@uchicago.edu>'

import os
import sys
import json
import boto3
from boto3.dynamodb.conditions import Key

# Import utility helpers
sys.path.insert(1, os.path.realpath(os.path.pardir))
import helpers

# Get configuration
from configparser import SafeConfigParser
# Get configuration
config = SafeConfigParser(os.environ)
config.read('restore_config.ini')

AWS_REGION = config.get('aws', 'AwsRegionName')
VAULT_NAME = config.get('S3', 'vault_name')
QUEUE_URL= config.get('QUEUE', 'restore_queue_url')
DYNAMODB_TABLE = config.get('DYNAMODB', 'annotations_table')
RESTORE_SNS= config.get('SNS', 'sns_restore_topic')
THAW_SNS= config.get('SNS', 'sns_thaw_topic')

# Create a new SQS client and specify AWS region
sqs = boto3.client('sqs', region_name=AWS_REGION)

# Create a new Glacier client
glacier = boto3.client('glacier', region_name=AWS_REGION)

# Create a new DynamoDB resource
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
table = dynamodb.Table(DYNAMODB_TABLE)


def update_archive_status(job_id):
    #while retriving from glacier, update archive_status to restoring for classification
    try:
        table.update_item(
            Key={
                'job_id': job_id
            },
            UpdateExpression='SET archive_status = :val1',
            ExpressionAttributeValues={
                ':val1': 'restoring'
            }
        )
    except Exception as e:
        print(f"An error occurred while trying to update the item in DynamoDB: {e}")
        return 

def retrieve_from_glacier(vault_name, archive_id):
    #https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/glacier.html
    #post message to thaw_sns, user 'Expedited' first then 'Standard'
    try:
        job_parameters = {
            'Type': 'archive-retrieval',
            'ArchiveId': archive_id,
            'Tier': 'Expedited',
            'SNSTopic': THAW_SNS
        }

        response = glacier.initiate_job(
            vaultName=vault_name,
            jobParameters=job_parameters
        )
        print(f"restored from glacier: {response['jobId']}")
        return response['jobId']

    except glacier.exceptions.InsufficientCapacityException:
        job_parameters['Tier'] = 'Standard'
        response = glacier.initiate_job(
            vaultName=vault_name,
            jobParameters=job_parameters
        )
        return response['jobId']

    except Exception as e:
        print(f"Error initiating Glacier retrieval job: {e}")
        return None

while True:
    messages = sqs.receive_message(QueueUrl=QUEUE_URL, MaxNumberOfMessages=10, WaitTimeSeconds=5)

    if 'Messages' in messages:
        for message in messages['Messages']:
            sns_message = json.loads(message['Body'])
            message_body = json.loads(sns_message['Message'])
            if 'user_id' in message_body:
                user_id = message_body['user_id']
                # Retrieve archiveId for the job from DynamoDB
                response = table.query(
            IndexName='user_id_index',
            KeyConditionExpression=Key('user_id').eq(user_id)
        )
                for item_res in  response['Items']:
                    if 'archive_status' not in item_res:
                        continue
                    elif item_res['archive_status'] =="completed":
                        archive_id = item_res['results_file_archive_id']
                        print(f"{item_res['job_id']}, archive id {archive_id} is archived. Restore in progress.")
                        # Initiate a retrieval job in Glacier
                        if archive_id:
                            job_id= retrieve_from_glacier(VAULT_NAME, archive_id)
                            if job_id:
                                update_archive_status(item_res['job_id'])
                    else:
                        print(f"{item_res['job_id']} archive status is {item_res['archive_status']}.skipped")
                        continue
               
            # Remove the processed message from SQS
            sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=message['ReceiptHandle'])


### EOF