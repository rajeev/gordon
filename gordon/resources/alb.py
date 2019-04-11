import six
import time
import json

import troposphere
from troposphere import elasticloadbalancingv2 as elb2, iam, awslambda, s3, certificatemanager as cert
from troposphere.validators import integer, tg_healthcheck_port
from .base import BaseResource
from gordon import utils
from gordon.contrib.helpers.resources import MaintenanceModeOn, MaintenanceModeOff

from gordon.contrib.helpers.resources import Sleep

from clint.textui import colored, puts, indent

class LambdaTargetGroup(troposphere.AWSObject):
    resource_type = "AWS::ElasticLoadBalancingV2::TargetGroup"

    props = {
        'HealthCheckIntervalSeconds': (integer, False),
        'HealthCheckPath': (str, False),
        'HealthCheckPort': (tg_healthcheck_port, False),
        'HealthCheckProtocol': (str, False),
        'HealthCheckTimeoutSeconds': (integer, False),
        'HealthyThresholdCount': (integer, False),
        'Matcher': (elb2.Matcher, False),
        'Name': (str, False),
        'Tags': (list, False),
        'TargetGroupAttributes': ([elb2.TargetGroupAttribute], False),
        'Targets': ([elb2.TargetDescription], False),
        'TargetType': (str, False),
        'UnhealthyThresholdCount': (integer, False),
    }


class FixedResponseConfig(troposphere.AWSProperty):
    props = {
        "ContentType": (str, True),
        "MessageBody": (str, True),
        "StatusCode": (str, True),
    }

class RedirectConfig(troposphere.AWSProperty):
    props = {
        "Host": (str, True),
        "Path": (str, True),
        "Port": (str, True),
        "Protocol": (str, True),
        "Query": (str, True),
        "StatusCode": (str, True),
    }

class Action(elb2.Action):
    props = {
        'Type': (str, True),
        'TargetGroupArn': (str, False),
        'FixedResponseConfig': (FixedResponseConfig, False),
        'RedirectConfig': (RedirectConfig, False),
    }

class ApplicationLoadBalancer(BaseResource):

    grn_type = "alb"

    # def get_enabled(self):
    #     """Returns if this stream is enable or not."""
    #     return ['DISABLED', 'ENABLED'][self._get_true_false('enabled')]
    #
    def get_function_name(self, name):
        """Returns a reference to the current alias of the lambda which will
        process this stream."""
        return self.project.reference(
            utils.lambda_friendly_name_to_grn(
                name
            )
        )

    def get_destination_arn(self, name):
        return troposphere.Ref(
            self.get_function_name(name)
        )

    def _valid_cf_name(self, *suffixes):
        return utils.valid_cloudformation_name(
            self.name,
            *suffixes
        )

    def register_resources_template(self, template: troposphere.Template):
        vpc = {}
        if self.settings.get('vpc'):
            vpc = vpc_id = self.project.get_resource('vpc::{}'.format(self.settings.get('vpc')))

            if isinstance(vpc.settings['security-groups'], troposphere.Ref):
                vpc.settings[
                    'security-groups']._type = 'List<AWS::EC2::SecurityGroup::Id>'

            if isinstance(vpc.settings['subnet-ids'], troposphere.Ref):
                vpc.settings['subnet-ids']._type = 'List<AWS::EC2::Subnet::Id>'

            vpc = dict(
                SecurityGroups=vpc.settings['security-groups'],
                Subnets=vpc.settings['subnet-ids']
            )
        else:
            #TODO: create a VPC here?
            pass

        lambda_version = 'lambda:contrib_helpers:maintenance:current'
        lambda_ref = troposphere.Ref(self.project.reference(lambda_version))


        mmon = template.add_resource(
            MaintenanceModeOn.create_with(
                utils.valid_cloudformation_name(self.name, "MMOn"),
                DependsOn = [
                    self.project.reference(lambda_version)
                ],
                lambda_arn=lambda_ref,
                Timestamp=int(time.time()),
                Project=self.project.name,
                FRule=self._valid_cf_name('alb-forward-rule'),
                MRule=self._valid_cf_name('alb-maintenance-rule'),
                Stack=troposphere.Join('-', [
                    troposphere.Ref('Stage'),
                    self.project.name,
                    'r'
                ])

            )
        )

        perm = template.add_resource(
            troposphere.awslambda.Permission(
                self._valid_cf_name('alb-tg', 'permission'),
                Action="lambda:InvokeFunction",
                FunctionName=self.get_destination_arn(self.settings.get('lambda')),
                Principal="elasticloadbalancing.amazonaws.com",
                # TODO: doesn't seem to work with CF; is this a security issue?
                #  yes, aws confifmed it is a CF bug; filed a ticket
                # SourceArn=tg.Ref(),
            )
        )


        #The Target Group
        tg = template.add_resource(LambdaTargetGroup(
            self._valid_cf_name('alb-tg'),
            DependsOn=[self._valid_cf_name('alb-tg', 'permission'), self.get_function_name(self.settings.get('lambda'))],
            TargetType="lambda",
            Targets=[
                elb2.TargetDescription(
                    self._valid_cf_name('alb-target-lambda'),
                    Id=troposphere.Ref(self.get_function_name(self.settings.get('lambda'))),
                )
            ],
        ))


        # The Load Balancer itself


        alb = template.add_resource(elb2.LoadBalancer(
            self.in_project_cf_name,
            Name=self.in_project_cf_name,
            DependsOn=[self._valid_cf_name('alb-tg')],
            **vpc
        ))



        # HTTP listener; redirects to HTTPS

        default_action = Action(
            self._valid_cf_name('alb-default-action'),
            Type='redirect',
            RedirectConfig=RedirectConfig(
                Host="#{host}",
                Path="/#{path}",
                Port="443",
                Protocol="HTTPS",
                Query="#{query}",
                StatusCode="HTTP_302"
            )
        )

        listener = template.add_resource(elb2.Listener(
            self._valid_cf_name('alb-listener'),
            DependsOn=[self._valid_cf_name('alb-tg'), self.get_function_name(self.settings.get('lambda'))],
            LoadBalancerArn=alb.Ref(),
            DefaultActions=[default_action],
            Port=80,
            Protocol="HTTP"
        ))

        # HTTPS Listener: has two rules: one for flowing traffic to Lambda; and a lower
        # priority rule for setting up maintenance mode

        service_default_action = Action(
            self._valid_cf_name('alb-default-action'),
            Type='fixed-response',
            FixedResponseConfig=FixedResponseConfig(
                ContentType="application/json",
                StatusCode="503",
                MessageBody=json.dumps({'EndOf':'TheLine'})
            )
        )

        ssl_listener = template.add_resource(elb2.Listener(
            self._valid_cf_name('alb-ssllistener'),
            DependsOn=[self._valid_cf_name('alb-tg'), self.get_function_name(self.settings.get('lambda'))],
            LoadBalancerArn=alb.Ref(),
            DefaultActions=[service_default_action],
            Port=443,
            Protocol="HTTPS",
            Certificates=[elb2.Certificate(CertificateArn=self.settings.get('certificate'))]
        ))

        ## The rule that forwards traffic to lambda

        tg_forward_action = Action(
            self._valid_cf_name('alb-forward-action'),
            Type='forward',
            TargetGroupArn=tg.Ref()
        )

        tg_forward_condition = elb2.Condition(
            self._valid_cf_name('alb-forward-condition'),
            Field="path-pattern",
            Values=['*']
        )

        template.add_resource(elb2.ListenerRule(
            self._valid_cf_name('alb-forward-rule'),
            Actions=[tg_forward_action],
            Conditions=[tg_forward_condition],
            ListenerArn=ssl_listener.Ref(),
            Priority=1
        ))

        # The rule for setting up maintenance mode

        tg_maintenance_action = Action(
            self._valid_cf_name('alb-maintenance-action'),
            Type='fixed-response',
            FixedResponseConfig=FixedResponseConfig(
                ContentType="application/json",
                StatusCode="503",
                MessageBody=json.dumps({'Down':'Maintenance'})
            )
        )

        tg_maintenance_condition = elb2.Condition(
            self._valid_cf_name('alb-maintenance-condition'),
            Field="path-pattern",
            Values=['*']
        )

        template.add_resource(elb2.ListenerRule(
            self._valid_cf_name('alb-maintenance-rule'),
            Actions=[tg_maintenance_action],
            Conditions=[tg_maintenance_condition],
            ListenerArn=ssl_listener.Ref(),
            Priority=100
        ))


        mmoff = template.add_resource(
            MaintenanceModeOff.create_with(
                utils.valid_cloudformation_name(self.name, "MMOff"),
                DependsOn = [
                    listener.name
                ],
                lambda_arn=lambda_ref,
                Timestamp=int(time.time()),
                Project=self.project.name,
                FRule = self._valid_cf_name('alb-forward-rule'),
                MRule = self._valid_cf_name('alb-maintenance-rule'),
                Stack=troposphere.Join('-', [
                    troposphere.Ref('Stage'),
                    self.project.name,
                    'r'
                ])
            )
        )

        if self._get_true_false('cli-output', 't'):
            template.add_output([
                troposphere.Output(
                        utils.valid_cloudformation_name("Clioutput", self.in_project_name),
                        Value=troposphere.Join("", ["http://", troposphere.GetAtt(alb, "DNSName")])
                )
            ])
