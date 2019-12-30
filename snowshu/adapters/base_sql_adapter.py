import sqlalchemy
from snowshu.logger import Logger
from snowshu.core.models.credentials import Credentials

logger=Logger().logger

class BaseSQLAdapter:

    REQUIRED_CREDENTIALS:iter
    ALLOWED_CREDENTIALS:iter

    def __init__(self):
        self.class_name=self.__class__.__name__

    @property
    def credentials(self)->dict:
        return self._credentials

    @credentials.setter
    def credentials(self,value:Credentials)->None:
        for cred in self.REQUIRED_CREDENTIALS:
            if value.__dict__[cred] == None:
                raise KeyError(f"{self.__class__.__name__} requires missing credential {cred}.")
        ALL_CREDENTIALS = self.REQUIRED_CREDENTIALS+self.ALLOWED_CREDENTIALS
        for val in [val for val in value.__dict__.keys() if (val not in ALL_CREDENTIALS and value.__dict__[val] is not None)]:
            raise KeyError(f"{self.__class__.__name__} received extra argument {val} this is not allowed")

        self._credentials=value

    def get_connection(self)->sqlalchemy.engine.base.Engine:
        if not self._credentials:
            raise KeyError('Adapter.get_connection called before setting Adapter.credentials')

        logger.debug(f'Aquiring {self.__class__.__name__} connection...')
        super().get_connection()
        conn_parts=[f"snowflake://{self.credentials.user}:{self.credentials.password}@{self.credentials.account}/{self.credentials.database}/"]
        conn_parts.append(self.credentials.schema if self.credentials.schema is not None else '')
        get_args=list()
        for arg in ('warehouse','role',):
            if self.credentials.__dict__[arg] is not None:
                get_args.append(f"{arg}={self.credentials.__dict__[arg]}")
        
        get_string = "?" + "&".join([arg for arg in get_args])
        conn_string = (''.join(conn_parts)) + get_string  

        engine = sqlalchemy.create_engine(conn_string,poolclass=NullPool)
        logger.debug('Done. New snowflake connection aquired.')
        logger.debug(f'conn string: {repr(engine.url)}')
        return engine
