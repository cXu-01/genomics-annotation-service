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

job_id='fsQg6kduHtg7-I0LCdhtG9uDtwuHgemJOYajd_9afjhRwETheH0pfcooYcLqCzmpsZMRZbC1LM6rs778KvePpOT1Eyud19uxGGN1WR8yh3ErYkqgRqQ4gJCO6ld8bHLY5xxbPBChUQ'
response = glacier.describe_job(vaultName=VAULT_NAME, jobId=job_id)

print(response)