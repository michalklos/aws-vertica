aws-vertica
===========

Python script using Fabric and Boto to manage deploy of a Vertica cluster into AWS.

It creates a standalone VPC environment. One node is designated as the Internet Gateway and
the bootstrap node where the administrative commands are run.

Prerequisites
===========

Python Packages:
pip install fabric
pip install boto

Boto Configuration File:
/etc/boto.cfg
[Credentials]
aws_access_key_id=<your_key>
aws_secret_access_key=<your_key>

AWS PEM file
~/.aws/<aws_region>.pem

Vertica License file
~/.aws/vlicense.dat

SSH Keys
~/.ssh/id_rsa.pub

Commands
===========

check whats going on
fab --set region='us-east-1' print_status

deploy a new cluster
fab --set region='us-east-1' deploy_cluster:total_nodes=3

deploy a new cluster using an existing elastic ip for bootstrap/gateway instance
fab --set region='us-east-1' deploy_cluster:total_nodes=3,eip_allocation_id=eipalloc-xxxxxx

deploy to an existing vpc cluster, it will consider the gateway node to be the bootstrap
 if there are existing nodes in the cluster, it will attempt to bring the number of
 nodes in the cluster to total_nodes
fab --set region='us-east-1' deploy_cluster:total_nodes=3,vpc_id=vpc-xxxxxxxx

