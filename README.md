# genomics-annotation-service

A refined web framework, based on Flask, developed specifically for the capstone project. It incorporates robust user authentication through Globus Auth, modular templates, and visually appealing styling provided by Bootstrap.

Directory Structure
/web - Holds the GAS web application files
/ann - Contains annotator files
/util - Comprises utility scripts for notifications, archival, and restoration processes
/aws - Contains AWS user data files
Archive Process (AWS Vault, SNS, SQS, S3, Glacier)
An SQS with a delay subscribes to a specific SNS, receiving a message upon annotation completion.
The SQS continually fetches messages linked to completed annotation jobs, retrieving job ID and user ID.
For non-premium users, the archive status in a given database table is updated to pending, the result file is uploaded to Glacier and concurrently deleted from S3. On successful upload, the archive status is updated and the archive ID is recorded.
The originating SQS message is deleted.
Restore Process (AWS Vault, SNS, SQS, EC2, S3, Glacier)
On user subscription confirmation, a message is dispatched to a specific SNS.
An SQS, subscribing to this SNS, fetches messages incessantly. A valid message triggers the extraction of user_id, and the scan of user's table records. Records with a specific archive status indicate a need for file restoration.
The restore message is deleted.
For records necessitating restoration, the archive ID is fetched from the table record, the file is retrieved from Glacier, and a message is sent to a specific SNS to notify Glacier of the completed retrieval.
An SQS, subscribing to the said SNS, uploads the restored files from Glacier to S3 and removes them from Glacier.
The database table is updated, removing the archive status and archive ID post completion of the process.
The thaw message is deleted.
Rationale
Scalability: The system uses the high message handling capacity of SQS and the automatic scalability of AWS Lambda, enabling it to auto-scale in response to workload fluctuations.
Stability: The system can operate and restore tasks, even when part of the system is down, owing to the separation of SNS and SQS. Messages that fail Lambda processing are retained in the queue for future attempts.
Maintenance: The system provides visibility into the origin of messages, simplifying maintenance and debugging.
Flexibility: The use of adaptable AWS services, such as SNS and SQS, empowers the application to easily adapt to changes.







