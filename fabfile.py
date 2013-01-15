from fabric.api import run,sudo,env,put,settings
import time
from boto import ec2,vpc,config
from boto.ec2.regioninfo import RegionInfo
from boto.exception import EC2ResponseError

import os

REGION_AMI_MAP={"us-east-1":"ami-1d048474"}
INSTANCE_TYPE='m3.xlarge'
ACCESS_KEY=config.get(section="Credentials", name = "aws_access_key_id")
SECRET_KEY=config.get(section="Credentials", name = "aws_secret_access_key")
CLUSTER_LICENSE_PATH="/etc/vertica/vlicense"
LOCAL_LICENSE_PATH="~/.aws/vlicense"
CLUSTER_KEY_PATH="/etc/vertica/aws.pem"
LOCAL_PUBLIC_KEY="~/.ssh/id_rsa.pub"
CLUSTER_USER="root"
DB_USER="dbadmin"
AUTHORIZED_IP_BLOCKS=['0.0.0.0/0']

env.region_info=RegionInfo(name=env.region, endpoint='ec2.{0}.amazonaws.com'.format(env.region))
env.key_filename = "~/.aws/{0}.pem".format(env.region)
env.key_pair = env.region

ec2_conn =ec2.connect_to_region(region_name=env.region)
vpc_conn =vpc.VPCConnection(region=env.region_info)

def print_status():
    """Prints whats going on in AWS
    """
    all_instances = [ i for r in ec2_conn.get_all_instances() for i in r.instances if i.state != 'terminated']
    
    
    print "Instances:"
    for instance in all_instances:
        instance_vitals=""
        instance_vitals+='\t ID: {0}'.format(instance.id)
        instance_vitals+='\n\t State: {0}'.format(instance.state)
        if instance.public_dns_name: instance_vitals+='\n\t Public DNS: {0}'.format(instance.public_dns_name)
        if instance.ip_address: instance_vitals+='\n\t Public IP: {0}'.format(instance.ip_address)
        if instance.private_dns_name: instance_vitals+='\n\t Private DNS: {0}'.format(instance.private_dns_name)
        if instance.private_ip_address: instance_vitals+='\n\t Private IP: {0}'.format(instance.private_ip_address)
        print "\n"+instance_vitals

    print "\nElastic IPs:"
    for address in ec2_conn.get_all_addresses():
        print address
        print address.allocation_id
    
    print "\nEBS Volumes:"
    for vol in ec2_conn.get_all_volumes():
        print vol
        print "\tStatus: {0}".format(vol.status)

    print "\nSecurity Groups:"
    for sg in ec2_conn.get_all_security_groups():
        print sg
        print "\tID: {0}".format(sg.id)
        print "\tVPC ID: {0}".format(sg.vpc_id)
    
    print "\nVPCs:"
    for v in vpc_conn.get_all_vpcs():
        print v

    print "\nSubnets:"
    for s in vpc_conn.get_all_subnets():
        print s
    


def deploy_cluster(num_nodes, vpc_id=None, db_name="dw", eip_allocation_id=None):
    """Deploy Bootstrap node along with VPC, Subnet and Elastic IP
       Add nodes to reach specified num_nodes
       eip_allocation_id : Elastic IP Allocation ID if you want to re-use existing IP
    """
    
    #get or create vpc
    if vpc_id:
        subnet=vpc_conn.get_all_subnets(filters=[("vpcId",vpc_id)])[0]
    else:
        subnet=__create_vpc()
    
    bootstrap_instance=None
    existing_instances=[i for r in ec2_conn.get_all_instances(filters={"subnet-id":subnet.id}) for i in r.instances if i.state != 'terminated']
    if existing_instances:
        #identify bootstrap based on presence of public ip
        for i in existing_instances:
            if i.ip_address:
                bootstrap_instance=i
                break
    else:
        #deploy new bootstrap
        print "Deploying bootstrap instance..."
        bootstrap_instance=__deploy_node(subnet_id=subnet.id)
        print "\tInstance : id:{0} private_ip_address:{1}".format(bootstrap_instance.id, bootstrap_instance.private_ip_address)
        
        if not eip_allocation_id:
            print "Creating and assigning elastic ip..."
            eip_allocation_id=ec2_conn.allocate_address(domain="vpc").allocation_id
        
        ec2_conn.associate_address(bootstrap_instance.id, None, eip_allocation_id)
        print "\tElastic Ip: allocation_id:{0} public_ip:{1}".format(eip_allocation_id, bootstrap_instance.ip_address)
        
        print "\nAuthorizing security group..."
        __authorize_security_group(bootstrap_instance.groups[0].id)

    #Print set up set up steps
    __setup_vertica(bootstrap=bootstrap_instance, db_name=db_name)
    
    print "Success!"
    print "Connect to the bootstrap node:"
    print "\tssh -i {0} {1}@{2}".format(env.key_filename, "root", bootstrap_instance.ip_address)
    print "Connect to the database:"
    print "\tvsql -U {0} -w {1} -h {2} -d {3}".format("dbadmin",db_name,bootstrap_instance.ip_address,db_name)
    
    add_nodes(total_nodes=num_nodes,vpc_id=vpc_id)

def add_nodes(total_nodes, vpc_id):
    print "Making sure cluster has {0} nodes".format(total_nodes)
    subnet=vpc_conn.get_all_subnets(filters=[("vpcId",vpc_id)])[0]
    
    #how many nodefs are there 
    existing_instances=[i for r in ec2_conn.get_all_instances(filters={"subnet-id":subnet.id}) for i in r.instances if i.state != 'terminated']
    bootstrap_instance=None
    for i in existing_instances:
        if i.ip_address:
            bootstrap_instance=i
            break
    print bootstrap_instance
    print "Cluster has {0} nodes, needs {1} more".format(len(existing_instances),int(total_nodes)-len(existing_instances))
    if int(total_nodes)-len(existing_instances) == 0:
        print "nothing to do"
        return
    #Add nodes
    #new_node_ips=[]
    node_ips=[i.private_ip_address for i in existing_instances]
    for i in range(0,int(total_nodes)-len(existing_instances)):
        new=__deploy_node(subnet_id=bootstrap_instance.subnet_id)
        node_ips.append(new.private_ip_address)
        
    __add_nodes_to_cluster(bootstrap_instance=bootstrap_instance, node_ips=node_ips)


def __add_nodes_to_cluster(bootstrap_instance, node_ips):
    """ Deploys new vertica node to VPC and then adds it to the cluster
    """
    print "Deploying new node"
    env.host=bootstrap_instance.ip_address
    env.user=CLUSTER_USER
    env.host_string= "{0}@{1}:22".format(env.user, env.host)

    
    print "Adding new nodes to cluster"
    __stitch_cluster(node_ips=node_ips)
    #sudo("/opt/vertica/sbin/vcluster -A {new_ips} -k {pem}".format(new_ips=','.join(node_ips), pem=CLUSTER_KEY_PATH))
    print "Nodes added successfully!"

def __setup_vertica(bootstrap, db_name):
    """ Runs set up commands on remote bootstrap node
    """
    print "Setting up cluster and creating database..."
    env.host=bootstrap.ip_address
    env.user=CLUSTER_USER
    env.host_string= "{0}@{1}:22".format(env.user, env.host)

    #transfer license file
    sudo("mkdir -p {0}".format(os.path.dirname(CLUSTER_LICENSE_PATH)))
    put(local_path=LOCAL_LICENSE_PATH,remote_path=CLUSTER_LICENSE_PATH,use_sudo=True)

    #transfer pem key
    put(local_path=env.key_filename,remote_path=CLUSTER_KEY_PATH,use_sudo=True,mode=0400)
    
    #stitch cluster
    __stitch_cluster(node_ips=[bootstrap.private_ip_address])

    #create EULA acceptance file
    sudo("echo 'S:a\nT:{0}\nU:500' > /opt/vertica/config/d5415f948449e9d4c421b568f2411140.dat".format(time.time()))
    
    __copy_ssh_keys(host=env.host,user=DB_USER)
    
    #create database
    env.user=DB_USER
    env.host_string= "{0}@{1}:22".format(env.user, env.host)
    
    run("/opt/vertica/bin/adminTools -t create_db -s {bootstrap_ip} -d {db_name} -p {db_password} -l {license_path}".format(bootstrap_ip=bootstrap.private_ip_address, db_name=db_name, db_password=db_name, license_path=CLUSTER_LICENSE_PATH))

def __stitch_cluster(node_ips):
    for ip in node_ips:
        run("ssh-keyscan -H {0} >> ~/.ssh/known_hosts".format(ip))

    node_ip_list=','.join(node_ips)
    sudo("/opt/vertica/sbin/vcluster -s {bootstrap_ip} -L {license_path} -k {key_path}".format(bootstrap_ip=node_ip_list, license_path=CLUSTER_LICENSE_PATH, key_path=CLUSTER_KEY_PATH))


def __copy_ssh_keys(host, user):
    """ Enables passwordless ssh for the user/host specified
    """
    env.host=host
    env.user=CLUSTER_USER
    env.host_string= "{0}@{1}:22".format(env.user, env.host)
    
    with settings(warn_only=True):
        user_home="/home/{0}".format(user)
        
        if sudo('ls {0}/.ssh/user.pub'.format(user_home)).return_code == 0:
            return
    sudo("mkdir -p {0}/.ssh/".format(user_home))
    put(LOCAL_PUBLIC_KEY, "{0}/.ssh/user.pub".format(user_home),use_sudo=True)
    sudo("cat {0}/.ssh/user.pub >> {0}/.ssh/authorized_keys".format(user_home))

def __create_vpc():
    """Sets up a VPC, Subnet, Internet Gateway, Route Table
       Returns the Subnet
    """
    print "Creating VPC..."
    b_vpc=vpc_conn.create_vpc('10.0.0.0/24')
    print "\tVPC : {0}".format(b_vpc.id)
    
    print "Creating Subnet..."
    subnet=vpc_conn.create_subnet(b_vpc.id, '10.0.0.0/25')
    print "\tSubnet : {0}".format(subnet.id)
    
    print "Creating and attaching Internet gateway..."
    internet_gateway=vpc_conn.create_internet_gateway()
    vpc_conn.attach_internet_gateway(internet_gateway.id, b_vpc.id)

    print "Associating route table..."
    route_table=vpc_conn.get_all_route_tables(filters=[("vpc-id",b_vpc.id)])[0]

    print "Creating route in route table..."
    vpc_conn.create_route(route_table_id=route_table.id, destination_cidr_block='0.0.0.0/0', gateway_id=internet_gateway.id)

    vpc_conn.associate_route_table(route_table.id, subnet.id)
    
    return subnet

def __authorize_security_group(sg_id):
    sg=ec2_conn.get_all_security_groups(group_ids=[sg_id])[0]
    try:
        sg.authorize(ip_protocol="icmp",from_port=0,to_port=-1,cidr_ip=AUTHORIZED_IP_BLOCKS)
        sg.authorize(ip_protocol="icmp",from_port=30,to_port=-1,cidr_ip=AUTHORIZED_IP_BLOCKS)
        sg.authorize(ip_protocol="tcp",from_port=22,to_port=22,cidr_ip=AUTHORIZED_IP_BLOCKS)
        sg.authorize(ip_protocol="tcp",from_port=80,to_port=80,cidr_ip=AUTHORIZED_IP_BLOCKS)
        sg.authorize(ip_protocol="tcp",from_port=443,to_port=443,cidr_ip=AUTHORIZED_IP_BLOCKS)
        sg.authorize(ip_protocol="tcp",from_port=4803,to_port=4805,cidr_ip=AUTHORIZED_IP_BLOCKS)
        sg.authorize(ip_protocol="tcp",from_port=5433,to_port=5434,cidr_ip=AUTHORIZED_IP_BLOCKS)
        sg.authorize(ip_protocol="tcp",from_port=5444,to_port=5444,cidr_ip=AUTHORIZED_IP_BLOCKS)
        sg.authorize(ip_protocol="tcp",from_port=5450,to_port=5450,cidr_ip=AUTHORIZED_IP_BLOCKS)
        sg.authorize(ip_protocol="udp",from_port=4803,to_port=4805,cidr_ip=AUTHORIZED_IP_BLOCKS)
    except EC2ResponseError:
        pass
    
def __deploy_node(subnet_id):
    """Deploy instance to specified subnet
    """
    ami_image_id=REGION_AMI_MAP[env.region]

    reservation = ec2_conn.run_instances(image_id=ami_image_id,
                                         instance_type=INSTANCE_TYPE,
                                         key_name=env.key_pair,
                                         subnet_id=subnet_id)

    instance = reservation.instances[0]
    
    while True:  # need to wait while instance.state is u'pending'
        print 'instance is {0}'.format(instance.state)
        instance.update()
        if (instance.state != u'pending'):
            break
        time.sleep(5)
    time.sleep(45)
    print 'Successfully created node in EC2'
    
    return instance


