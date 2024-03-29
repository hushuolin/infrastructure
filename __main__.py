"""An AWS Python Pulumi program"""

import pulumi
import pulumi_aws as aws
import json

config = pulumi.Config()

# Fetch the config values
prefix = config.require("prefix")
cidrBlock = config.require("cidrBlock")
numOfSubnets = config.require_int("numOfSubnets")
cidr_first_two_octets = cidrBlock.split('.')[0] + '.' + cidrBlock.split('.')[1]
cidr_prefix_length = config.require_int("cidrPrefixLength")
region = config.require("region")
numOfBrokers = config.require("numOfBrokers")
sshName = config.require("sshName")

# --- Network Setup ---

# Create a vpc
vpc = aws.ec2.Vpc(f"{prefix}-vpc",
    cidr_block=cidrBlock,
    tags={
        "Name": f"{prefix}-vpc",
    })

# Create an internet gateway
igw = aws.ec2.InternetGateway(f"{prefix}-igw",
    vpc_id=vpc.id,
    tags={
        "Name": f"{prefix}-igw",
    })

# Create public and private subnets
public_subnets = []
private_subnets = []
# Fetch available availability zones
azs = aws.get_availability_zones(state="available")
max_azs = len(azs.names)
# Don't allow numOfSubnets exceed the max available zone in the current region
numOfSubnets = min(max_azs, numOfSubnets)
for i in range(numOfSubnets):
    az = f"{region}{chr(97+i)}"  # This will give us '{us-east-1}{a}', '{us-east-1}{b}', '{us-east-1}{c} ....'
    public_subnet = aws.ec2.Subnet(f"{prefix}-public-subnet-{az}",
        vpc_id=vpc.id,
        cidr_block=f"{cidr_first_two_octets}.{i*2}.0/{cidr_prefix_length}",
        availability_zone=az,
        map_public_ip_on_launch=True, 
        tags={
            "Name": f"{prefix}-public-subnet-{az}",
        }
    )
    public_subnets.append(public_subnet)

    private_subnet = aws.ec2.Subnet(f"{prefix}-private-subnet-{az}",
        vpc_id=vpc.id,
        cidr_block=f"{cidr_first_two_octets}.{i*2+1}.0/{cidr_prefix_length}",
        availability_zone=az,
        tags={
            "Name": f"{prefix}-private-subnet-{az}",
        }
    )
    private_subnets.append(private_subnet)

# Create public and private route tables
public_rt = aws.ec2.RouteTable(f"{prefix}-public-rt",
    vpc_id=vpc.id,
    tags={
        "Name": f"{prefix}-public-rt",
    })

private_rt = aws.ec2.RouteTable(f"{prefix}-private-rt",
    vpc_id=vpc.id,
    tags={
        "Name": f"{prefix}-private-rt",
    })

# Associate subnets with route tables
for index, subnet in enumerate(public_subnets):
    aws.ec2.RouteTableAssociation(f"{prefix}-public-rta-{index}",
        subnet_id=subnet.id,
        route_table_id=public_rt.id,
    )

for index, subnet in enumerate(private_subnets):
    aws.ec2.RouteTableAssociation(f"{prefix}-private-rta-{index}",
        subnet_id=subnet.id,
        route_table_id=private_rt.id,
    )

# Route for intenet gateway
aws.ec2.Route("public-route",
    route_table_id=public_rt.id,
    destination_cidr_block="0.0.0.0/0",
    gateway_id=igw.id,
)

# --- EC2 Setup for MSK Client ---
# Create an IAM role for the EC2 client
ec2_role = aws.iam.Role(f"{prefix}-ec2-role",
    assume_role_policy=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {
                "Service": "ec2.amazonaws.com"
            },
            "Action": "sts:AssumeRole"
        }]
    }))

# Attach the policy to the role
ec2_role_policy_attachment = aws.iam.RolePolicyAttachment(f"{prefix}-ec2-role-policy-attachment",
    role=ec2_role.name,
    policy_arn="arn:aws:iam::aws:policy/AmazonMSKFullAccess")

ec2_msk_cluster_role_policy_attachment = aws.iam.RolePolicyAttachment(f"{prefix}-ec2-msk-cluster-policy-attachment",
    role=ec2_role.name,
    policy_arn="arn:aws:iam::742465305217:policy/MSK_cluster")


# Security group for the EC2 client machine with SSH access
ec2_sg = aws.ec2.SecurityGroup(f"{prefix}-client-sg",
    vpc_id=vpc.id,
    description='Security Group for MSK Client',
    ingress=[
        # SSH access rule
        aws.ec2.SecurityGroupIngressArgs(
            description='SSH access',
            from_port=22,
            to_port=22,
            protocol='tcp',
            cidr_blocks=['0.0.0.0/0']  
        ),
    ],
    egress=[
        aws.ec2.SecurityGroupEgressArgs(
            from_port=0,
            to_port=0,
            protocol='-1',
            cidr_blocks=['0.0.0.0/0']
        )
    ],
    tags={
        "Name": f"{prefix}-client-sg",
    })

# Create an EC2 instance profile for the IAM role
ec2_instance_profile = aws.iam.InstanceProfile(f"{prefix}-ec2-instance-profile",
    role=ec2_role.name)

# Select the appropriate AMI for Amazon Linux 2
ami = aws.ec2.get_ami(most_recent=True,
    owners=["amazon"],
    filters=[{"name": "name", "values": ["amzn2-ami-hvm-*-x86_64-gp2"]}])

# Create an EC2 instance for the MSK client
msk_client_instance = aws.ec2.Instance(f"{prefix}-client",
    instance_type="t2.micro",
    ami=ami.id,
    key_name=sshName,
    subnet_id=public_subnets[0].id,
    iam_instance_profile=ec2_instance_profile.name,
    vpc_security_group_ids=[ec2_sg.id],
    tags={
        "Name": f"{prefix}-MSKTutorialClient",
    })


# --- MSK Setup ---

# Security group for MSK
msk_security_group = aws.ec2.SecurityGroup(f"{prefix}-msk-sg",
    vpc_id=vpc.id,
    description='Security Group for MSK',
    ingress=[
        aws.ec2.SecurityGroupIngressArgs(
            description='Kafka',
            from_port=9098,
            to_port=9098,
            protocol='tcp',
            security_groups=[ec2_sg.id]
        ),
    ],
    egress=[
        aws.ec2.SecurityGroupEgressArgs(
            from_port=0,
            to_port=0,
            protocol='-1',
            cidr_blocks=["0.0.0.0/0"]
        ),
    ],
    tags={
        "Name": f"{prefix}-msk-sg",
    }
)

### Create MSK cluster
msk_cluster = aws.msk.Cluster(f"{prefix}-msk-cluster",
    kafka_version="3.2.0",
    number_of_broker_nodes=numOfBrokers,
    broker_node_group_info=aws.msk.ClusterBrokerNodeGroupInfoArgs(
        instance_type="kafka.m5.large",
        client_subnets=[subnet.id for subnet in private_subnets],
        security_groups=[msk_security_group.id],
        storage_info=aws.msk.ClusterBrokerNodeGroupInfoStorageInfoArgs(
            ebs_storage_info=aws.msk.ClusterBrokerNodeGroupInfoStorageInfoEbsStorageInfoArgs(
                volume_size=1000,
            ),
        ),
    ),
    tags={
        "Name": f"{prefix}-msk-cluster",
    }
)

# Create an IAM role for MSK
msk_role = aws.iam.Role(f"{prefix}-msk-role",
    assume_role_policy=json.dumps({
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "sts:AssumeRole",
                "Principal": {
                    "Service": "kafka.amazonaws.com"
                }
            }
        ]
    }))

# Attach MSK policy to MSK role
msk_role_policy_attachment = aws.iam.RolePolicyAttachment(f"{prefix}-msk-role-policy-attachment",
    role=msk_role.name,
    policy_arn="arn:aws:iam::aws:policy/AmazonMSKFullAccess")

msk_cluster_role_policy_attachment = aws.iam.RolePolicyAttachment(f"{prefix}-msk-cluster-policy-attachment",
    role=msk_role.name,
    policy_arn="arn:aws:iam::742465305217:policy/MSK_cluster")


# --- Lambda Function ---

# # IAM role for the Lambda function
# lambda_role = aws.iam.Role("lambdaRole",
#     assume_role_policy=json.dumps({
#         "Version": "2012-10-17",
#         "Statement": [{
#             "Effect": "Allow",
#             "Principal": {"Service": "lambda.amazonaws.com"},
#             "Action": "sts:AssumeRole"
#         }]
#     }))

# # Attach the policy to the role
# aws.iam.RolePolicyAttachment("sns-lambda-attachment",
#     role=lambda_role.name,
#     policy_arn="arn:aws:iam::aws:policy/AmazonMSKFullAccess")

# aws.iam.RolePolicyAttachment("cloudwatch-lambda-attachment",
#     role=lambda_role.name,
#     policy_arn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole")

# # Assuming your Lambda code is zipped in 'lambda_function.zip'
# lambdaPath = config.require("lambdaPath")

# lambda_function = aws.lambda_.Function("myLambdaFunction",
#     role=lambda_role.arn,
#     runtime="python3.8",  
#     handler="fetch_consumer_complaints.lambda_handler",
#     timeout=100,
#     code=pulumi.FileArchive(lambdaPath),
#     memory_size=1024,
#     environment=aws.lambda_.FunctionEnvironmentArgs(
#         variables={
#             "msk_bootstrap_servers": msk_cluster.bootstrap_brokers_tls,
#             "msk_cluster_arn": msk_cluster.arn
#         }) 
#     )

# --- Outputs ---

pulumi.export('vpc_id', vpc.id)
pulumi.export('msk_cluster_arn', msk_cluster.arn)
pulumi.export('msk_cluster_endpoint', msk_cluster.bootstrap_brokers_tls)
# pulumi.export('client_instance_id', msk_client_instance.id)
# pulumi.export('client_instance_public_ip', msk_client_instance.public_ip)
# pulumi.export('client_instance_public_dns', msk_client_instance.public_dns)


