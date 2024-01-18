# AWS Infrastructure with Pulumi (Python)

This repository contains the infrastructure code for an AWS Python Pulumi Project. Pulumi allows us to define infrastructure as code using familiar programming languages. This project uses Python to create resources on AWS.

## Prerequisites

Before you begin, ensure you have the following installed:
- [Pulumi](https://www.pulumi.com/docs/install/)
- [Python](https://www.python.org/downloads/) (version 3.x or later)
- [AWS CLI](https://aws.amazon.com/cli/) with AWS account configured

## Setup and Installation

### 1. Clone the Repository
```
git clone git@github.com:hushuolin/infrastructure.git
cd infrastructure
```

### 2. Install Dependencies
```
pip install -r requirements.txt
```

## Project Configuration

### 1. Initialize and Select a Stack
(Optional, if you need a specific stack)
```
pulumi stack init <stack-name>
pulumi stack select <stack-name>
```

### 2. Configure AWS
Set the AWS profile and region in Pulumi:
```
pulumi config set aws:profile <profile-name>
pulumi config set aws:region <desired-region>
```

### 3. Configure Variables
Edit Pulumi.<stack-name>.yaml as needed for your configuration.


## Deployment and Destroying Infrastructure

### 1. Preview Deployment
Review changes before deploying:
```
pulumi preview
```

### 2. Deploy Infrastructure
Execute the deployment:
```
pulumi up
```

### 3. Destroying Infrastructure
To safely tear down your AWS resources:
```
pulumi destroy
```

## Contributing
Contributions are welcome! Please read our Contributing Guide for more information.

## License
This project is licensed under the MIT License.


