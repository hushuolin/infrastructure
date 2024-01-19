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

# Create numOfSubnets public and private subnets
public_subnets = []
private_subnets = []
# Fetch available availability zones
azs = aws.get_availability_zones(state="available")
max_azs = len(azs.names)
# Don't allow numOfSubnets exceed the max available zone in the current region
numOfSubnets = min(max_azs, numOfSubnets)
for i in range(numOfSubnets):
    az = f"{region}{chr(97+i)}"  # This will give us '{us-east-1}{a}', '{us-east-1}{b}', '{us-east-1}{c} ....'
    # Create public subnets
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
    # Create private subnets
    private_subnet = aws.ec2.Subnet(f"{prefix}-private-subnet-{az}",
        vpc_id=vpc.id,
        cidr_block=f"{cidr_first_two_octets}.{i*2+1}.0/{cidr_prefix_length}",
        availability_zone=az,
        tags={
            "Name": f"{prefix}-private-subnet-{az}",
        }
    )
    private_subnets.append(private_subnet)

# Create public route table
public_rt = aws.ec2.RouteTable(f"{prefix}-public-rt",
    vpc_id=vpc.id,
    tags={
        "Name": f"{prefix}-public-rt",
    })

# # Associate public subnets with the public route table
for index, subnet in enumerate(public_subnets):
    aws.ec2.RouteTableAssociation(f"{prefix}-public-rta-{index}",
        subnet_id=subnet.id,
        route_table_id=public_rt.id,
    )

# Create private route table
private_rt = aws.ec2.RouteTable(f"{prefix}-private-rt",
    vpc_id=vpc.id,
    tags={
        "Name": f"{prefix}-private-rt",
    })

# Associate private subnets with the private route table
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

# --- MSK Setup ---

### Security group for MSK
msk_security_group = aws.ec2.SecurityGroup(f"{prefix}-msk-sg",
    vpc_id=vpc.id,
    description='Security Group for MSK',
    ingress=[
        aws.ec2.SecurityGroupIngressArgs(
            description='Kafka',
            from_port=9094,
            to_port=9094,
            protocol='tcp',
            cidr_blocks=['0.0.0.0/0']
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
        client_subnets=[subnet.id for subnet in public_subnets],
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
msk_role_policy_attachment = aws.iam.RolePolicyAttachment(f"{prefix}-msk-policy-attachment",
    role=msk_role.name,
    policy_arn="arn:aws:iam::aws:policy/AmazonMSKFullAccess")

# --- Outputs ---

pulumi.export('vpc_id', vpc.id)
pulumi.export('msk_cluster_arn', msk_cluster.arn)
pulumi.export('msk_cluster_endpoint', msk_cluster.bootstrap_brokers_tls)

