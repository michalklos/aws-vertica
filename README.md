aws-vertica
===========

Python script using Fabric and Boto to manage deploy Vertica cluster into AWS.

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
~/.aws/<raws_egion>.pem

Vertica License file
~/.aws/vlicense.dat

SSH Keys
~/.ssh/id_rsa.pub

Commands
===========

#check whats going on
fab --set region='us-east-1' print_status

#deploy a new cluster
fab --set region='us-east-1' deploy_cluster:num_nodes=2

#deploy a new cluster using an existing elastic ip for bootstrap/gateway instance
fab --set region='us-east-1' deploy_cluster:num_nodes=2,eip_allocation_id=eipalloc-1fcdf375

#deploy a bootsrap instance to an existing vpc cluster
fab --set region='us-east-1' deploy_cluster:num_nodes=2,vpc_id=vpc-316f515b

#add nodes to an existing cluster:
fab --set region='us-east-1' add_nodes:num_nodes=2,vpc_id=vpc-c3d0e9a9



