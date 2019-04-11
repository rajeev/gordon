import time
import boto3
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

from cfnresponse import send, SUCCESS

def toggle_maintenance_mode(Stack, FRule, MRule, forward):
    cfn = boto3.client('cloudformation', region_name="us-west-1")

    try:
        forward_rule = cfn.describe_stack_resource(
            StackName=Stack,
            LogicalResourceId=FRule
        )['StackResourceDetail']['PhysicalResourceId']

        maintenance_rule = cfn.describe_stack_resource(
            StackName=Stack,
            LogicalResourceId=MRule
        )['StackResourceDetail']['PhysicalResourceId']

        elbv2 = boto3.client('elbv2', region_name="us-west-1")
        elbv2.set_rule_priorities(
            RulePriorities=[
                dict(RuleArn=forward_rule, Priority=1 if forward else 10),
                dict(RuleArn=maintenance_rule, Priority=10 if forward else 1)
            ]
        )
    except Exception as e:
        print("Exception in Maintenance Mode Update")
        print(e)

def handler(event, context):
    ResourceType = event['ResourceType']
    Stack = event['ResourceProperties'].get('Stack', None)
    FRule = event['ResourceProperties'].get('FRule', None)
    MRule = event['ResourceProperties'].get('MRule', None)
    PhysicalResourceId = event['PhysicalResourceId']

    if event['RequestType'] in ['Delete']:
        send(event, context, SUCCESS, {}, physicalResourceId=PhysicalResourceId)
        return

    assert ResourceType.startswith('Custom::MaintenanceMode')
    toggle_maintenance_mode(Stack, FRule, MRule, forward=ResourceType.endswith('Off'))

    send(event, context, SUCCESS, {}, physicalResourceId=PhysicalResourceId)
