"""Keep operational HTTP access logs without persisting search query strings."""
import logging


class RedactQuery(logging.Filter):
    def filter(self, record):
        if not isinstance(record.args,tuple) or len(record.args)!=5:
            return False  # Fail closed if the server's access-log contract changes.
        client,method,target,version,status=record.args
        if not isinstance(target,str):
            return False
        record.args=(client,method,target.partition('?')[0],version,status)
        return True


def install():
    logger=logging.getLogger('uvicorn.access')
    if not any(isinstance(item,RedactQuery) for item in logger.filters):
        logger.addFilter(RedactQuery())
