"""Used to annotate table types."""
import typing

class Column:
    """Allows for custom sql types/options."""
    def __init__(self, sql):
        self.sql = sql


if typing.TYPE_CHECKING:
    # pylint: disable=unused-argument
    def varchar(length: int) -> typing.Type[str]:
        """length: length of varchar"""
        return str
else:
    def varchar(length: int) -> Column:
        """length: length of varchar"""
        return Column(f'varchar({length})')

if typing.TYPE_CHECKING:
    integer = int2 = int4 = int8 = smallint = bigint = int
    text = str
    real = double_precision = float
    boolean = bool
else:
    integer = Column('integer')
    int2 = Column('int2')
    int4 = Column('int4')
    int8 = Column('int8')
    smallint = Column('smallint')
    bigint = Column('bigint')
    text = Column('text')
    real = Column('real')
    double_precision = Column('double precision')
    timestamp = Column('timestamp')
    boolean = Column('boolean')
