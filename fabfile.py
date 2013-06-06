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
LOCAL_PUBLIC_KEY="~/.ssh/id_rsa.pub"
CLUSTER_USER="root"
DB_USER="dbadmin"
AUTHORIZED_IP_BLOCKS_HTTP=['0.0.0.0/0']
AUTHORIZED_IP_BLOCKS_SSH=['0.0.0.0/0']
AUTHORIZED_IP_BLOCKS_DB=['0.0.0.0/0']
DB_PATH="/vertica/data"
DB_CATALOG="/vertica/data"
DB_NAME="dw"
DB_PW="MakeThisSecure!"

env.region_info=RegionInfo(name=env.region, endpoint='ec2.{0}.amazonaws.com'.format(env.region))
env.key_pair = env.cluster_name

env.key_filename = "~/.aws/{0}/{1}.pem".format(env.region, env.key_pair)

CLUSTER_KEY_PATH="/etc/vertica/{0}.pem".format(env.key_pair)

ec2_conn=ec2.connect_to_region(region_name=env.region)
vpc_conn=vpc.VPCConnection(region=env.region_info)
node_filter={'tag:ClusterName': env.cluster_name, 'tag:NodeType':'Vertica'}
vpc_node_filter={'tag:ClusterName': env.cluster_name}

def print_status(show_all="False"):
    """Prints whats going on in AWS
    """
    
    #for i in r.instances if i.state != 'terminated'
    node_instances=[ i for r in ec2_conn.get_all_instances(filters=node_filter) for i in r.instances]
    node_vpcs=vpc_conn.get_all_vpcs(filters=vpc_node_filter)
    all_instances=[ i for r in ec2_conn.get_all_instances() for i in r.instances]
    all_vpcs=vpc_conn.get_all_vpcs()

    show_instances=node_instances
    show_vpcs=node_vpcs
    
    if show_all=="True":
        show_instances=all_instances
        show_vpcs=all_vpcs

    print "Instances:"
    for instance in show_instances:
        instance_vitals=""
        instance_vitals+='\t ID: {0}'.format(instance.id)
        instance_vitals+='\n\t State: {0}'.format(instance.state)
        if instance.public_dns_name: instance_vitals+='\n\t Public DNS: {0}'.format(instance.public_dns_name)
        if instance.ip_address: instance_vitals+='\n\t Public IP: {0}'.format(instance.ip_address)
        if instance.private_dns_name: instance_vitals+='\n\t Private DNS: {0}'.format(instance.private_dns_name)
        if instance.private_ip_address: instance_vitals+='\n\t Private IP: {0}'.format(instance.private_ip_address)
        if instance.ip_address: 
            instance_vitals+='\n\t SSH: ssh -i {0} {1}@{2}'.format(env.key_filename, CLUSTER_USER, instance.ip_address)
            instance_vitals+= "\n\tvsql -U {0} -w {1} -h {2} -d {3}".format("dbadmin",DB_PW,instance.ip_address, DB_NAME)
        instance_vitals += '\n\t Tags:' 
        for tag in sorted(instance.tags):
            instance_vitals += '\n\t\t  %s : %s' % (tag, instance.tags[tag])
        print "\n"+instance_vitals

    print "\nVPCs:"
    for v in show_vpcs:
        print "VPC:"
        print "\tID: " + str(v.id)
        subnet=vpc_conn.get_all_subnets(filters=[("vpcId",v.id)])[0]
        print "\tSubnetID: " + str(subnet.id)
        print "\tTags:"
        for tag in sorted(v.tags):
            print '\t\t  %s : %s' % (tag, v.tags[tag])
            

def terminate_cluster(vpc_id, kill_vpc="False"):
    """ Terminate a cluster with extreme prejudice
    """
    subnet=vpc_conn.get_all_subnets(filters=[("vpcId",vpc_id)])[0]
    existing_instances=[i for r in ec2_conn.get_all_instances(filters={"subnet-id":subnet.id}) for i in r.instances if i.state != 'terminated']
    print "Killing {0} instances...".format(len(existing_instances))
    for i in existing_instances:
        i.terminate()
        while True:  # need to wait while instance.state is u'pending'
            print 'instance is {0}'.format(i.state)
            i.update()
            if (i.state == u'terminated'):
                break
            time.sleep(5)
        print "\tInstance terminated"
    
    if kill_vpc=="True":
        print "Deleting VPC..."
        vpc_conn.delete_vpc(vpc_id)
    print "Success"

def deploy_cluster(total_nodes,  vpc_id=None, eip_allocation_id=None):
    """Deploy Bootstrap node along with VPC, Subnet and Elastic IP
       Add nodes to reach specified num_nodes
       eip_allocation_id : Elastic IP Allocation ID if you want to re-use existing IP
    """
    
    #get or create vpc
    if not vpc_id:
        sn_vpc=__create_vpc()
        subnet=sn_vpc[0]
        vpc_id=sn_vpc[1].id
    
    bootstrap_instance=__get_bootstrap_instance(vpc_id=vpc_id)
    
    if not bootstrap_instance:
        #deploy new bootstrap
        subnet=vpc_conn.get_all_subnets(filters=[("vpcId",vpc_id)])[0]
        print "Deploying bootstrap instance..."
        bootstrap_instance=__deploy_node(subnet_id=subnet.id)
        print "\tInstance : id:{0} private_ip_address:{1}".format(bootstrap_instance.id, bootstrap_instance.private_ip_address)
        
        if not eip_allocation_id:
            print "Creating and assigning elastic ip..."
            eip_allocation_id=ec2_conn.allocate_address(domain="vpc").allocation_id
        
        ec2_conn.associate_address(bootstrap_instance.id, None, eip_allocation_id)
        while not bootstrap_instance.ip_address:
            print "Waiting for ip..."
            bootstrap_instance.update()
            time.sleep(10)
        print "\tElastic Ip: allocation_id:{0} public_ip:{1}".format(eip_allocation_id, bootstrap_instance.ip_address)
        print "Waiting additional 30 seconds for safety"
        time.sleep(30)
        authorize_security_group(vpc_id)
        #make sure we can access the box
        __copy_ssh_keys(host=bootstrap_instance.ip_address,user=CLUSTER_USER)
        __setup_vertica(bootstrap=bootstrap_instance)


    __make_cluster_whole(total_nodes=total_nodes,vpc_id=vpc_id)
    
    print "Success!"
    print "Connect to the bootstrap node:"
    print "\tssh -i {0} {1}@{2}".format(env.key_filename, "root", bootstrap_instance.ip_address)
    print "Connect to the database:"
    print "\tvsql -U {0} -w {1} -h {2} -d {3}".format("dbadmin",DB_PW,bootstrap_instance.ip_address, DB_NAME)

def __set_fabric_env(host,user):
    env.host=host
    env.user=user
    env.host_string="{0}@{1}:22".format(env.user, env.host)

def __make_cluster_whole(total_nodes, vpc_id):
    """ Makes sure that cluster in vpc has total_nodes number of nodes
    """
    print "Making sure cluster has {0} nodes".format(total_nodes)
    bootstrap_instance=__get_bootstrap_instance(vpc_id)
    
    #how many nodes are there 
    existing_instances=[i for r in ec2_conn.get_all_instances(filters={"subnet-id":bootstrap_instance.subnet_id}) for i in r.instances if i.state != 'terminated']

    if bootstrap_instance is None:
        raise Exception("No bootstrap instance while trying to make cluster whole")
    print bootstrap_instance
    print "Cluster has {0} nodes, needs {1} more".format(len(existing_instances),int(total_nodes)-len(existing_instances))
    if int(total_nodes)-len(existing_instances) == 0:
        print "nothing to do"
        return
    #Add nodes
    new_node_ips=[]
    #node_ips=[i.private_ip_address for i in existing_instances]
    for i in range(0,int(total_nodes)-len(existing_instances)):
        new=__deploy_node(subnet_id=bootstrap_instance.subnet_id)
        new_node_ips.append(new.private_ip_address)
    
    print "Adding new nodes to cluster"
    __set_fabric_env(bootstrap_instance.ip_address, CLUSTER_USER)
    __add_to_existing_cluster(bootstrap_ip=bootstrap_instance.ip_address, new_node_ips=new_node_ips)
    
    print "Nodes added successfully!"

def __setup_vertica(bootstrap):
    """ Runs set up commands on remote bootstrap node
    """
    print "Setting up cluster and creating database..."
    bootstrap.update()

    __set_fabric_env(bootstrap.ip_address, CLUSTER_USER)
    time.sleep(30)
    __copy_ssh_keys(host=bootstrap.ip_address,user=CLUSTER_USER)
    #transfer license file
    sudo("mkdir -p {0}".format(os.path.dirname(CLUSTER_LICENSE_PATH)))
    #transfer pem key
    #if put works, remove s3cmd and put Put back in
    #sudo("s3cmd get --force s3://gaia-toolbox/{0}.pem /etc/vertica/".format(env.key_pair))
    #sudo("chmod 400 /etc/vertica/{0}.pem".format(env.key_pair))
    
    #local("rsync -aC -e \"ssh -o StrictHostKeyChecking=no -i {0}\" {1} {2}@{3}:{4}".format(env.key_filename,env.key_filename,env.user,env.host,CLUSTER_KEY_PATH))
    put(local_path=env.key_filename,remote_path=CLUSTER_KEY_PATH,use_sudo=True,mirror_local_mode=True)
    put(local_path=LOCAL_LICENSE_PATH,remote_path=CLUSTER_LICENSE_PATH,use_sudo=True)
    
    #authorize yourself for passwordless ssh
    #sudo("ssh-keygen -y -f {0} >> /{1}/.ssh/authorized_keys".format(CLUSTER_KEY_PATH,CLUSTER_USER))

    #clear out any erroneous rsa ids
    #__recreate_rsa_id(CLUSTER_USER)
    
    #stitch cluster
    __stitch_cluster(bootstrap_ip=bootstrap.private_ip_address)

    #create EULA acceptance file
    sudo("echo 'S:a\nT:{0}\nU:500' > /opt/vertica/config/d5415f948449e9d4c421b568f2411140.dat".format(time.time()))

    #make sure we can access the box
    __copy_ssh_keys(host=env.host,user=DB_USER)    
    __create_database(bootstrap)

def __create_database(bootstrap):
    #create database
    __set_fabric_env(bootstrap.ip_address, DB_USER)

    #Usage: create_db [options]
    #Options:
    #-h, --help            show this help message and exit
    #-s NODES, --hosts=NODES   comma-separated list of hosts to participate in database
    #-d DB, --database=DB  Name of database to be created
    #-c CATALOG, --catalog_path=CATALOG  Path of catalog directory[optional] if not using compat21
    #-D DATA, --data_path=DATA  Path of data directory[optional] if not using compat21
    #-p DBPASSWORD, --password=DBPASSWORD  Database password in single quotes [optional]
    #-l LICENSEFILE, --license=LICENSEFILE  Database license [optional]
    #-P POLICY, --policy=POLICY Database restart policy [optional]
    #--compat21            Use Vertica 2.1 method using node names instead of  hostnames
    
    run("/opt/vertica/bin/adminTools -t create_db -s {bootstrap_ip} -d {db_name} -p {db_password} -l {license_path} -D {db_path} -c {db_catalog}".format(bootstrap_ip=bootstrap.private_ip_address, db_name=DB_NAME, db_password=DB_PW, license_path=CLUSTER_LICENSE_PATH, db_path=DB_PATH, db_catalog=DB_CATALOG))


def __stitch_cluster(bootstrap_ip):
    user_home=__get_home(CLUSTER_USER)
    run("ssh-keyscan {0} >> {1}/.ssh/known_hosts".format(bootstrap_ip, user_home))
    sudo("/opt/vertica/sbin/vcluster -s {node_ips} -L {license_path} -k {key_path}".format(node_ips=bootstrap_ip, license_path=CLUSTER_LICENSE_PATH, key_path=CLUSTER_KEY_PATH))

def __add_to_existing_cluster(bootstrap_ip, new_node_ips):
    user_home=__get_home(CLUSTER_USER)
    time.sleep(45) #wait for last node's ssh to come up
    for ip in new_node_ips:
        run("ssh-keyscan {0} >> {1}/.ssh/known_hosts".format(ip, user_home))

    node_ip_list=','.join(new_node_ips)
    sudo("/opt/vertica/sbin/vcluster -A {node_ips} -k {key_path}".format(node_ips=node_ip_list, key_path=CLUSTER_KEY_PATH))        

    __set_fabric_env(bootstrap_ip, DB_USER)

    #Usage: db_add_node [options]
    #Options:
    #-h, --help            show this help message and exit
    #-d DB, --database=DB  Name of database to be restarted
    #-s HOSTS, --hosts=HOSTS Comma separated list of hosts to add to database
    #-p DBPASSWORD, --password=DBPASSWORD Database password in single quotes
    #-a AHOSTS, --add=AHOSTS Comma separated list of hosts to add to database
    #-i, --noprompts       do not stop and wait for user input(default false)
    #--compat21            Use Vertica 2.1 method using node names instead of hostnames
    run("/opt/vertica/bin/adminTools -t db_add_node -a {new_node_ips} -d {db_name} -p {db_password} -i".format(new_node_ips=node_ip_list, db_name=DB_NAME, db_password=DB_PW))

    #Usage: rebalance_data [options]
    #Options:
    #-h, --help            show this help message and exit
    #-d DBNAME, --dbname=DBNAME database name
    #-k KSAFETY, --ksafety=KSAFETY specify the new k value to use
    #-p PASSWORD, --password=PASSWORD
    #--script  Don't re-balance the data, just provide a script for later use.
    #TODO: rebalance prompts for password but nothing seems to work
    #run("/opt/vertica/bin/adminTools -t rebalance_data -d {db_name} -p {db_password} -k 1".format(db_name=DB_NAME, db_password=DB_NAME))   

def __get_home(user):
    if user==CLUSTER_USER:
        user_home="/{0}".format(user)
    else:
        user_home="/home/{0}".format(user)
    return user_home

def __get_bootstrap_instance(vpc_id):
    subnet=vpc_conn.get_all_subnets(filters=[("vpcId",vpc_id)])[0]
    
    bootstrap_instance=None
    existing_instances=[i for r in ec2_conn.get_all_instances(filters={"subnet-id":subnet.id}) for i in r.instances if i.state != 'terminated']
    if existing_instances:
        #identify bootstrap based on presence of public ip
        for i in existing_instances:
            if i.ip_address:
                bootstrap_instance=i
                break
    return bootstrap_instance

def __copy_ssh_keys(host, user):
    """ Enables passwordless ssh for the user/host specified
    """
    
    __set_fabric_env(host, CLUSTER_USER)
    
    with settings(warn_only=True):
        user_home=__get_home(user)
        
        if sudo('ls {0}/.ssh/user.pub'.format(user_home)).return_code == 0:
            return
    sudo("mkdir -p {0}/.ssh/".format(user_home))
    put(LOCAL_PUBLIC_KEY, "{0}/.ssh/user.pub".format(user_home),use_sudo=True)
    sudo("cat {0}/.ssh/user.pub >> {0}/.ssh/authorized_keys".format(user_home))

    #__recreate_rsa_id(user)

def __create_vpc():
    """Sets up a VPC, Subnet, Internet Gateway, Route Table
       Returns a tuple with Subnet and VPC
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
    
    b_vpc.add_tag('ClusterName', env.cluster_name)
    return (subnet, b_vpc)

def __authorize_ip(sg,ip_protocol,from_port,to_port,cidr_ip):
    try:
        sg.authorize(ip_protocol=ip_protocol,from_port=from_port,to_port=to_port,cidr_ip=cidr_ip)
    except EC2ResponseError:
        pass
    
def authorize_security_group(vpc_id):
    print "Authorizing security groups"
    instance=__get_bootstrap_instance(vpc_id)
    sg=ec2_conn.get_all_security_groups(group_ids=[instance.groups[0].id])[0]
    for ip in AUTHORIZED_IP_BLOCKS_DB:
        __authorize_ip(sg,ip_protocol="icmp",from_port=0,to_port=-1,cidr_ip=ip)
        __authorize_ip(sg,ip_protocol="icmp",from_port=30,to_port=-1,cidr_ip=ip)
        __authorize_ip(sg,ip_protocol="tcp",from_port=443,to_port=443,cidr_ip=ip)
        __authorize_ip(sg,ip_protocol="tcp",from_port=4803,to_port=4805,cidr_ip=ip)
        __authorize_ip(sg,ip_protocol="tcp",from_port=5433,to_port=5434,cidr_ip=ip)
        __authorize_ip(sg,ip_protocol="tcp",from_port=5444,to_port=5444,cidr_ip=ip)
        __authorize_ip(sg,ip_protocol="tcp",from_port=5450,to_port=5450,cidr_ip=ip)
        __authorize_ip(sg,ip_protocol="udp",from_port=4803,to_port=4805,cidr_ip=ip)
    for ip in AUTHORIZED_IP_BLOCKS_SSH:
        __authorize_ip(sg,ip_protocol="tcp",from_port=22,to_port=22,cidr_ip=ip)
    for ip in AUTHORIZED_IP_BLOCKS_HTTP:
        __authorize_ip(sg,ip_protocol="tcp",from_port=80,to_port=80,cidr_ip=ip)


def __deploy_node(subnet_id):
    """Deploy instance to specified subnet
    """
    ami_image_id=REGION_AMI_MAP[env.region]

    reservation = ec2_conn.run_instances(image_id=ami_image_id,
                                         instance_type=INSTANCE_TYPE,
                                         key_name=env.key_pair,
                                         subnet_id=subnet_id)

    instance = reservation.instances[0]
    
    failures=0
    while True:  # need to wait while instance.state is u'pending'
        print 'instance is {0}'.format(instance.state)
        try:
            instance.update()
            if (instance.state != u'pending'):
                break
        except EC2ResponseError:
            print "Error connecting to AWS... retrying..."
            failures+=1
            if failures==5:
                raise Exception("Couldnt get status of instance {0} from AWS".format(instance.id))
        time.sleep(5)
    time.sleep(45)
    print 'Successfully created node in EC2'

    
    instance.add_tag('ClusterName',env.cluster_name)
    instance.add_tag('NodeType','Vertica')
    instance.add_tag('Name','Vertica.'+env.cluster_name+'.'+instance.id)
    return instance


