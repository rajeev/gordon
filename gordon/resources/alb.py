import six

import troposphere
from troposphere import elasticloadbalancingv2 as elb2, iam, awslambda, s3
from troposphere.validators import integer, tg_healthcheck_port
from .base import BaseResource
from gordon import utils

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


        template.add_resource(
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

        action = elb2.Action(
            self._valid_cf_name('alb-action'),
            Type='forward',
            TargetGroupArn=tg.Ref()
        )

        alb = template.add_resource(elb2.LoadBalancer(
            self.in_project_cf_name,
            Name=self.in_project_cf_name,
            DependsOn=[self._valid_cf_name('alb-tg')],
            **vpc
        ))

        listener = template.add_resource(elb2.Listener(
            self._valid_cf_name('alb-listener'),
            DependsOn=[self._valid_cf_name('alb-tg'), self.get_function_name(self.settings.get('lambda'))],
            LoadBalancerArn=alb.Ref(),
            DefaultActions=[action],
            Port=80,
            Protocol="HTTP"
        ))

        if self._get_true_false('cli-output', 't'):
            template.add_output([
                troposphere.Output(
                        utils.valid_cloudformation_name("Clioutput", self.in_project_name),
                        Value=troposphere.Join("", ["http://", troposphere.GetAtt(alb, "DNSName")])
                )
            ])
