from aws_cdk import (
    core as _core,
    aws_apigateway as _apigateway,
    aws_dynamodb as _dynamodb,
    aws_events as _events,
    aws_events_targets as _events_targets,
    aws_lambda as _lambda
)


class Serverless:
    def __init__(self, scope: _core.Construct) -> None:
        self.scope = scope

    def create_application(self, id, resource_handlers, dynamo_table):
        code = _lambda.Code.asset('lambda/.dist/lambda.zip')

        if bool(dynamo_table):
            ddb_table = self.create_ddb_table(dynamo_table)
        else:
            ddb_table = {}

        if len(resource_handlers) > 0:
            restapi = _apigateway.RestApi(
                self.scope, '{}-api'.format(id), rest_api_name='{}-api'.format(id)
            )

            for resource_handler in resource_handlers:

                handler = resource_handler['handler']
                readonly = resource_handler.get('readonly', False) or False
                memory_size = resource_handler.get('memory_size', 512) or 512

                if resource_handler.get('path'):
                    path = resource_handler['path']
                    methods = resource_handler['methods']
                    if ['GET'] == methods:
                        readonly = True

                    self.create_resource_handler(
                        name=self.create_name(id, handler),
                        handler=handler,
                        memory_size=memory_size,
                        code=code,
                        api=restapi,
                        path=path,
                        methods=methods,
                        table=ddb_table,
                        readonly=readonly,
                    )

                elif resource_handler.get('schedule'):
                    function = self.create_function(
                        name=self.create_name(id, handler),
                        handler=handler,
                        memory_size=memory_size,
                        code=code,
                        table=ddb_table,
                        readonly=readonly,
                    )

                    rule_name = '{}-rule'.format(self.create_name(id, handler))

                    scheduled_rule = _events.Rule(
                        self.scope,
                        rule_name,
                        rule_name=rule_name,
                        schedule=_events.Schedule.rate(
                            duration=_core.Duration.minutes(1)
                        ),
                    )
                    scheduled_rule.add_target(_events_targets.LambdaFunction(function))
                else:
                    self.create_function(
                        name=self.create_name(id, handler),
                        handler=handler,
                        code=code,
                        table=ddb_table,
                        readonly=readonly,
                    )

    def create_name(self, id, handler):
        return '{}-{}-function'.format(
            id, handler.split('.')[1].replace('.', '').replace('_', '-')
        ).lower()

    def create_ddb_table(self, dynamo_table):
        table_name = dynamo_table['table_name']
        partition_key = dynamo_table['partition_key']
        sort_key = dynamo_table.get('sort_key')
        if sort_key:
            ddb_table = _dynamodb.Table(
                self.scope,
                table_name,
                table_name=table_name,
                billing_mode=_dynamodb.BillingMode.PAY_PER_REQUEST,
                partition_key=_dynamodb.Attribute(
                    name=partition_key['name'], type=partition_key['type']
                ),
                sort_key=_dynamodb.Attribute(
                    name=sort_key['name'], type=sort_key['type']
                ),
                removal_policy=_core.RemovalPolicy.DESTROY,
            )
        else:
            ddb_table = _dynamodb.Table(
                self.scope,
                table_name,
                table_name=table_name,
                billing_mode=_dynamodb.BillingMode.PAY_PER_REQUEST,
                partition_key=_dynamodb.Attribute(name=GAME, type=STR),
                removal_policy=_core.RemovalPolicy.DESTROY,
            )

        indexes = dynamo_table.get('indexes', [])
        for index in indexes:
            gsi_partition_key = index['partition_key']
            gsi_sort_key = index['sort_key']
            ddb_table.add_global_secondary_index(
                index_name=index['index_name'],
                partition_key=_dynamodb.Attribute(
                    name=gsi_partition_key['name'], type=gsi_partition_key['type']
                ),
                sort_key=_dynamodb.Attribute(
                    name=gsi_sort_key['name'], type=gsi_sort_key['type']
                ),
            )
        return ddb_table

    def create_resource_handler(
            self,
            name,
            handler,
            api,
            path,
            methods,
            code,
            table,
            memory_size=512,
            readonly=True,
    ):

        function = self.create_function(
            name=name,
            handler=handler,
            memory_size=memory_size,
            code=code,
            table=table,
            readonly=readonly,
        )

        api_resource = api.root.resource_for_path(path)

        for method in methods:
            api_resource.add_method(method, _apigateway.LambdaIntegration(function))

    def create_function(
            self, name, handler, code, table, memory_size=512, readonly=True
    ):
        has_table = bool(table)

        if has_table:
            envs = {'TABLE_NAME': table.table_name}
        else:
            envs = {}

        function = _lambda.Function(
            self.scope,
            name,
            function_name=name,
            runtime=_lambda.Runtime.PYTHON_3_7,
            memory_size=memory_size,
            code=code,
            handler=handler,
            tracing=_lambda.Tracing.ACTIVE,
            environment=envs,
        )

        if has_table and readonly:
            table.grant_read_data(function)
        elif has_table and not readonly:
            table.grant_read_write_data(function)

        return function
