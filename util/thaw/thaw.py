# thaw.py
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
from boto3.dynamodb.conditions import Attr


# Get configuration
from configparser import SafeConfigParser
config = SafeConfigParser(os.environ)
config.read('thaw_config.ini')

# Add
AWS_REGION = config.get('aws', 'AwsRegionName')
VAULT_NAME = config.get('S3', 'vault_name')
RESULTS_BUCKET = config.get('S3', 'results_bucket')
DYNAMODB_TABLE = config.get('DYNAMODB', 'annotations_table')
QUEUE_URL= config.get('QUEUE', 'thaw_queue_url')

# Create a new Glacier client
glacier = boto3.client('glacier', region_name=AWS_REGION)

# Create a new S3 client
s3 = boto3.client('s3', region_name=AWS_REGION)

# Create a new DynamoDB resource
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
table = dynamodb.Table(DYNAMODB_TABLE)

# Create a new SQS client and specify AWS region
sqs = boto3.client('sqs', region_name=AWS_REGION)



# Download archive from Glacier to S3
def download_archive(vault_name, job_id, s3_bucket, s3_key):
    response = glacier.get_job_output(vaultName=vault_name, jobId=job_id)
    bytes_data =response['body'].read()
    s3.put_object(Body=bytes_data, Bucket=s3_bucket, Key=s3_key)

# Delete archive from Glacier
# https://docs.aws.amazon.com/amazonglacier/latest/dev/deleting-an-archive.html
def delete_archive(vault_name, archive_id):
    glacier.delete_archive(vaultName=vault_name,archiveId=archive_id)

while True:
    # Long polling
    messages = sqs.receive_message(QueueUrl=QUEUE_URL, MaxNumberOfMessages=10, WaitTimeSeconds=5)

    if 'Messages' in messages:
        for message in messages['Messages']:
            sns_message = json.loads(message['Body'])
            glacier_message = json.loads(sns_message['Message'])
            # Get necessary details from Glacier job message
            glacier_job_id = glacier_message['JobId']
            archive_id = glacier_message['ArchiveId']
            vault_name = glacier_message['VaultARN'].split(':')[-1]
            status = glacier_message['StatusCode']
            if status == 'Succeeded':
                response = table.scan(FilterExpression=Attr('results_file_archive_id').eq(archive_id))
                if 'Items' in response:
                    for item in response['Items']:
                        try:
                            job_id = item['job_id']
                            s3_key = item['s3_key_result_file']
                            # Download the archive from Glacier to S3
                            download_archive(VAULT_NAME, glacier_job_id, RESULTS_BUCKET, s3_key)
                            # Delete the archive from Glacier
                            delete_archive(VAULT_NAME, archive_id)
                            # Update DynamoDB to remove results_file_archive_id and archive_status
                            table.update_item(
                                Key={
                                    'job_id': job_id
                                },
                                UpdateExpression='REMOVE results_file_archive_id, archive_status'
                            )
                            print(f" job id {job_id} has been restored successfully. results_file_archive_id and archive_status has been removed from table and files has been uploaded to S3")
                        except Exception as e:
                            print(f"error occured: {e}")
            # Remove the processed message from SQS
            sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=message['ReceiptHandle'])
