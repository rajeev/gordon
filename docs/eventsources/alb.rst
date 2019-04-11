Application Load Balancer
================================

Application Load Balancer.

In theory, it sets up an ALB along with required permissions, within the specified vpc. This is extremely useful if you simply want to use frameworks like starlette, fastapi, etc, without the overhead of configuring the URLs with API Gateway.

Also, some users have expressed concern over the long term cost of using API Gateway. According to them, ALB seems to be a cheaper alternative for API Gateway.

.. _alb-anatomy:

Anatomy of the integration
----------------------------------

 .. code-block:: yaml

  application-load-balancer:

    { ALB_NAME }:
      description: { STRING }
      cli-output: { BOOLEAN }
      vpc: { VPC ID }
      lambda: { target lambda }
      certificate: { acm certificate arn }
