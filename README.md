# genomics-annotation-service

An advanced web framework, designed on the principles of [Flask](http://flask.pocoo.org/).It comes with advanced user authentication mechanisms using [Globus Auth](https://docs.globus.org/api/auth), modular templates for flexibility and custom styling options powered by [Bootstrap](http://getbootstrap.com/). 

## Directory Structure

- `/web` - Contains the main GAS web application files and the REST API endpoints developed with Flask.
- `/ann` - Hosts the annotator files responsible for processing and managing data annotations. Annotated data can provide valuable insights and aid in machine learning tasks.
- `/util` - Comprises utility scripts for timely notifications, archival, and restoration processes, enhancing user experience and data reliability.
- `/aws` - Stores AWS user data files securely, ensuring data privacy and integrity with AWS Vault.

## Technology Stack
Our application leverages various cutting-edge technologies and AWS services for superior performance and scalability:
- Flask and React.js for developing the backend and frontend of the application respectively.
- Globus Auth for robust user authentication.
- AWS Vault for managing and storing secrets and protecting sensitive data.
- AWS SNS (Simple Notification Service) and SQS (Simple Queue Service) for managing and processing application messages.
- AWS EC2 (Elastic Compute Cloud) for scalable and secure application hosting.
- AWS S3 (Simple Storage Service) for storing and retrieving any amount of data at any time from around the globe.
- AWS Glacier for cost-effective, long-term data archival.

## Archive Process (AWS Vault, SNS, SQS, S3, Glacier)

1. An SQS with a delay is configured to subscribe to a dedicated SNS. Upon completion of annotation, a message is dispatched to this SNS.
2. The SQS operates continually, fetching messages linked to completed annotation jobs. From these messages, job ID and user ID are extracted.
3. If the user is a non-premium one, the archive status in the corresponding database table is marked as pending. The result file is then uploaded to Glacier for long-term storage and simultaneously removed from S3 to free up storage space. Once the upload is confirmed, the archive status is updated to completed and the archive ID is saved for future reference.
4. Post-processing, the original SQS message is deleted, maintaining the queue's efficiency.

## Restore Process (AWS Vault, SNS, SQS, EC2, S3, Glacier)

1. Upon a user confirming their subscription, a message is dispatched to a dedicated SNS.
2. An SQS, listening to this SNS, fetches messages incessantly. When a valid message is detected, it triggers the extraction of user_id. This is followed by a comprehensive scan of the user's table records. Records with a specific archive status indicate a need for file restoration.
3. The restore message is then promptly deleted.
4. For records necessitating restoration, the archive ID is fetched from the table record. The file is then retrieved from Glacier and a message is dispatched to a designated SNS to inform Glacier of the completed retrieval.
5. An SQS, listening to this SNS, uploads the restored files from Glacier to S3 and removes them from Glacier, ensuring cost-effectiveness.
6. The database table is updated post the completion of the process, removing the archive status and archive ID.
7. The thaw message is then deleted, maintaining queue efficiency.

## Rationale

- **Scalability**: By leveraging the high message handling capacity of SQS and the automatic scalability of AWS Lambda, our system auto-scales in response to workload fluctuations.
- **Stability**: Our system ensures continuous operation and the ability to restore tasks, even when part of the system encounters a downtime, thanks to the distinct separation of SNS and SQS. Messages failing Lambda processing are retained in the queue for future processing.
- **Maintenance**: Our system simplifies maintenance and debugging by providing clear visibility into the origin of messages and their respective statuses.
- **Flexibility**: The use of versatile AWS services, such as SNS and SQS, along with Flask and React.js empowers our application to adapt readily to changes and updates.
