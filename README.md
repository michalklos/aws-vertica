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


Example output
==============

$ fab --set region='us-east-1' deploy_cluster:total_nodes=3,eip_allocation_id=eipalloc-xxxxxxxx
Creating VPC...
	VPC : vpc-xxxxxxxx
Creating Subnet...
	Subnet : subnet-xxxxxxxx
Creating and attaching Internet gateway...
Associating route table...
Creating route in route table...
Deploying bootstrap instance...
instance is pending
instance is pending
instance is pending
instance is pending
instance is pending
instance is pending
instance is pending
instance is pending
instance is pending
instance is pending
instance is pending
Successfully created node in EC2
	Instance : id:i-xxxxxxxx private_ip_address:10.0.0.92
	Elastic Ip: allocation_id:eipalloc-xxxxxxxx public_ip:None

Authorizing security group...
Setting up cluster and creating database...
[root@xxx.xxx.xxx.xxx:22] sudo: mkdir -p /etc/vertica
[root@xxx.xxx.xxx.xxx:22] put: /home/mklos/.aws/vlicense -> /etc/vertica/vlicense
[root@xxx.xxx.xxx.xxx:22] put: /home/mklos/.aws/us-east-1.pem -> /etc/vertica/aws.pem
[root@xxx.xxx.xxx.xxx:22] run: ssh-keyscan -H 10.0.0.92 >> ~/.ssh/known_hosts
[root@xxx.xxx.xxx.xxx:22] out: # 10.0.0.92 SSH-2.0-OpenSSH_5.3

[root@xxx.xxx.xxx.xxx:22] sudo: /opt/vertica/sbin/vcluster -s 10.0.0.92 -L /etc/vertica/vlicense -k /etc/vertica/aws.pem
[root@xxx.xxx.xxx.xxx:22] out: STEP 1 of 5: Building keyless ssh for dbadmin and copying to all nodes
[root@xxx.xxx.xxx.xxx:22] out: INFO: 22: Copying and resetting permissions to .ssh directory for:   dbadmin@10.0.0.92
[root@xxx.xxx.xxx.xxx:22] out: STEP 2 of 5: Copying the Vertica license to all nodes
[root@xxx.xxx.xxx.xxx:22] out: STEP 3 of 5: Configuring spread and copying to all nodes
[root@xxx.xxx.xxx.xxx:22] out: Stopping spread daemon: [  OK  ]

[root@xxx.xxx.xxx.xxx:22] out: Starting spread daemon: spread (pid  2269) is running...
[root@xxx.xxx.xxx.xxx:22] out: [  OK  ]
[root@xxx.xxx.xxx.xxx:22] out: STEP 4 of 5: Configuring admintools.conf and copying to all nodes
[root@xxx.xxx.xxx.xxx:22] out: STEP 5 of 5: Restarting agent on all nodes
[root@xxx.xxx.xxx.xxx:22] out: Stopping vertica agent: 
[root@xxx.xxx.xxx.xxx:22] out: starting agent
[root@xxx.xxx.xxx.xxx:22] out: OK for user: dbadmin
[root@xxx.xxx.xxx.xxx:22] out: INFO: 0: stitch completed successfully

[root@xxx.xxx.xxx.xxx:22] sudo: echo 'S:a
T:1358371544.95
U:500' > /opt/vertica/config/d5415f948449e9d4c421b568f2411140.dat
[root@xxx.xxx.xxx.xxx:22] sudo: ls /home/dbadmin/.ssh/user.pub
[root@xxx.xxx.xxx.xxx:22] out: ls: cannot access /home/dbadmin/.ssh/user.pub: No such file or directory


Warning: sudo() received nonzero return code 2 while executing 'ls /home/dbadmin/.ssh/user.pub'!

[root@xxx.xxx.xxx.xxx:22] sudo: mkdir -p /home/dbadmin/.ssh/
[root@xxx.xxx.xxx.xxx:22] put: /home/mklos/.ssh/id_rsa.pub -> /home/dbadmin/.ssh/user.pub
[root@xxx.xxx.xxx.xxx:22] sudo: cat /home/dbadmin/.ssh/user.pub >> /home/dbadmin/.ssh/authorized_keys
[dbadmin@xxx.xxx.xxx.xxx:22] run: /opt/vertica/bin/adminTools -t create_db -s 10.0.0.92 -d dw -p dw -l /etc/vertica/vlicense
[dbadmin@xxx.xxx.xxx.xxx:22] out: Database with 1  or 2 nodes cannot be k-safe and it may lose data if it crashes
[dbadmin@xxx.xxx.xxx.xxx:22] out: Distributing changes to cluster.
[dbadmin@xxx.xxx.xxx.xxx:22] out: 			10.0.0.92 OK [vertica][(6, 1, 0)][000][x86_64]
[dbadmin@xxx.xxx.xxx.xxx:22] out: 	Creating database dw
[dbadmin@xxx.xxx.xxx.xxx:22] out: 	Node Status: v_dw_node0001: (DOWN) 
[dbadmin@xxx.xxx.xxx.xxx:22] out: 	Node Status: v_dw_node0001: (INITIALIZING) 
[dbadmin@xxx.xxx.xxx.xxx:22] out: 	Node Status: v_dw_node0001: (VALIDATING LICENSE) 
[dbadmin@xxx.xxx.xxx.xxx:22] out: 	Node Status: v_dw_node0001: (UP) 
[dbadmin@xxx.xxx.xxx.xxx:22] out: 	Creating database nodes
[dbadmin@xxx.xxx.xxx.xxx:22] out: 	Node Status: v_dw_node0001: (UP) 
[dbadmin@xxx.xxx.xxx.xxx:22] out: Database dw created successfully.

Making sure cluster has 3 nodes
Instance:i-a53411d4
Cluster has 1 nodes, needs 2 more
instance is pending
instance is pending
instance is pending
instance is pending
instance is pending
instance is pending
instance is pending
instance is pending
instance is pending
instance is pending
instance is pending
instance is pending
Successfully created node in EC2
instance is pending
instance is pending
instance is pending
instance is pending
instance is pending
instance is pending
instance is pending
instance is pending
instance is pending
instance is pending
instance is pending
Successfully created node in EC2
Adding new nodes to cluster
[root@xxx.xxx.xxx.xxx:22] run: ssh-keyscan -H 10.0.0.92 >> ~/.ssh/known_hosts
[root@xxx.xxx.xxx.xxx:22] out: # 10.0.0.92 SSH-2.0-OpenSSH_5.3

[root@xxx.xxx.xxx.xxx:22] run: ssh-keyscan -H 10.0.0.67 >> ~/.ssh/known_hosts
[root@xxx.xxx.xxx.xxx:22] out: # 10.0.0.67 SSH-2.0-OpenSSH_5.3

[root@xxx.xxx.xxx.xxx:22] run: ssh-keyscan -H 10.0.0.108 >> ~/.ssh/known_hosts
[root@xxx.xxx.xxx.xxx:22] out: # 10.0.0.108 SSH-2.0-OpenSSH_5.3

[root@xxx.xxx.xxx.xxx:22] sudo: /opt/vertica/sbin/vcluster -s 10.0.0.92,10.0.0.67,10.0.0.108 -L /etc/vertica/vlicense -k /etc/vertica/aws.pem
[root@xxx.xxx.xxx.xxx:22] out: STEP 1 of 5: Building keyless ssh for dbadmin and copying to all nodes
[root@xxx.xxx.xxx.xxx:22] out: INFO: 22: Copying and resetting permissions to .ssh directory for:   dbadmin@10.0.0.92
[root@xxx.xxx.xxx.xxx:22] out: INFO: 22: Copying and resetting permissions to .ssh directory for:   dbadmin@10.0.0.67
[root@xxx.xxx.xxx.xxx:22] out: INFO: 22: Copying and resetting permissions to .ssh directory for:   dbadmin@10.0.0.108
[root@xxx.xxx.xxx.xxx:22] out: STEP 2 of 5: Copying the Vertica license to all nodes
[root@xxx.xxx.xxx.xxx:22] out: STEP 3 of 5: Configuring spread and copying to all nodes
[root@xxx.xxx.xxx.xxx:22] out: Stopping spread daemon: [  OK  ]

[root@xxx.xxx.xxx.xxx:22] out: Stopping spread daemon: [  OK  ]

[root@xxx.xxx.xxx.xxx:22] out: Stopping spread daemon: [  OK  ]

[root@xxx.xxx.xxx.xxx:22] out: Starting spread daemon: spread (pid  4027) is running...
[root@xxx.xxx.xxx.xxx:22] out: [  OK  ]
[root@xxx.xxx.xxx.xxx:22] out: Starting spread daemon: spread (pid  1928) is running...
[root@xxx.xxx.xxx.xxx:22] out: [  OK  ]
[root@xxx.xxx.xxx.xxx:22] out: Starting spread daemon: spread (pid  1912) is running...
[root@xxx.xxx.xxx.xxx:22] out: [  OK  ]
[root@xxx.xxx.xxx.xxx:22] out: STEP 4 of 5: Configuring admintools.conf and copying to all nodes
[root@xxx.xxx.xxx.xxx:22] out: STEP 5 of 5: Restarting agent on all nodes
[root@xxx.xxx.xxx.xxx:22] out: Stopping vertica agent: 
[root@xxx.xxx.xxx.xxx:22] out: starting agent
[root@xxx.xxx.xxx.xxx:22] out: OK for user: dbadmin
[root@xxx.xxx.xxx.xxx:22] out: Stopping vertica agent: 
[root@xxx.xxx.xxx.xxx:22] out: starting agent
[root@xxx.xxx.xxx.xxx:22] out: OK for user: dbadmin
[root@xxx.xxx.xxx.xxx:22] out: Stopping vertica agent: 
[root@xxx.xxx.xxx.xxx:22] out: starting agent
[root@xxx.xxx.xxx.xxx:22] out: OK for user: dbadmin
[root@xxx.xxx.xxx.xxx:22] out: INFO: 0: stitch completed successfully

Nodes added successfully!
Success!
Connect to the bootstrap node:
	ssh -i ~/.aws/us-east-1.pem root@xxx.xxx.xxx.xxx
Connect to the database:
	vsql -U dbadmin -w dw -h xxx.xxx.xxx.xxx -d dw

Done.
Disconnecting from xxx.xxx.xxx.xxx... done.
Disconnecting from dbadmin@xxx.xxx.xxx.xxx... done.
