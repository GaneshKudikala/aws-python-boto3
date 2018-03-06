#!/usr/bin/python
import socket
import urllib2
from datetime import datetime, timedelta
import boto3
from botocore.exceptions import ClientError

ec2 = boto3.resource('ec2')

def image_cleanup(timedelta_=timedelta(days=365)):
    boto3conn = boto3.resource("ec2", region_name="eu-west-1")
    query_result = list(boto3conn.images.filter(Owners=['self']))
    for image in query_result:
        icd = datetime.strptime(image.creation_date, '%Y-%m-%dT%H:%M:%S.000Z')
        if datetime.now() - icd > timedelta_:
            try:
                image.deregister()
            except ClientError:
                continue


def resolve_ip(host):
    return socket.gethostbyname(host)

def determine_instance(ip, host):
    instances = []
    filters = [{'Name': 'ip-address', 'Values': [ip]}]
    do_query = list(ec2.instances.filter(Filters=filters).limit(1))

    if not do_query:
        instances.append({
            'name': 'unknown',
            'image_id': 'unknown',
            'public_dns_name': host,
            'status': 'unknown',
            'dns_health': dns_check(host)
        })
        return instances

    for instance in do_query:
        instance_state = instance.state['Name']
        health_check = dns_check(host)

        if instance_state == 'stopped' and create_ami(instance):
            terminate(instance)
            instance_state = 'terminated'

        instances.append({
            'name': instance.instance_id,
            'image_id': instance.image_id,
            'public_dns_name': host,
            'status': instance_state,
            'dns_health': health_check
        })
    return instances

def dns_check(dns):
    if dns == '':
        return 'dns check failed'

    try:
        request = urllib2.Request('http://' + dns)
        urllib2.urlopen(request)
    except urllib2.HTTPError as e:
        if e.code !=500:
            return 'passed'
        else:
            return 'http check failed'
    except urllib2.URLError:
        return 'connection error'
    else:
        return 'passed'


def create_ami(instance):
    try:
        image = instance.create_image(
            InstanceId=instance.instance_id,
            Name=instance.instance_id + '-' + datetime.now().strftime('%H%m%S%d%M%Y')
        )
        image.wait_until_exists()
        image_tag = {'Key': 'opsworks',
                     'Value': 'done by Mikhail Kurtagin at ' + datetime.now().strftime('%H:%m:%S %d/%M/%Y')}
        image.create_tags(
            Tags=[
                image_tag
            ]
        )
        return True
    except ClientError:
        return False


def terminate(instance):
    instance.terminate()
    instance.wait_until_terminated()


def report(instance):
    dc = '\033[1;m'
    yc = '\033[1;43m'
    gc = '\033[1;42m'
    rc = '\033[1;41m'
    name_ = instance['name']
    image_id_ = instance['image_id']
    dns_name_ = instance['public_dns_name']
    status_ = instance['status']

    if status_ == 'running':
        status_ = gc + status_ + dc
    elif status_ == 'terminated':
        status_ = rc + status_ +dc
    else:
        status_ = yc + status_ +dc

    health_ = instance['dns_health']

    if health_ == 'passed':
        health_ = gc + health_ + dc
    elif health_ == 'dns check failed':
        health_ = rc + health_ + dc
    else:
        health_ = yc + health_ + dc

    print name_, image_id_, status_, dns_name_, health_


image_cleanup(timedelta(days=7))

host_data = [(resolve_ip(d.strip()), d.strip()) for d in open('hosts.list', 'r')]


instance_ls = []
for i in host_data:
    result = determine_instance(i[0], i[1])
    instance_ls.extend(result)

[report(ins) for ins in instance_ls]
