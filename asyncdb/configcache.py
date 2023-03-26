"""Module that contains the class that will reduce calls to postgres as much as possible. Has no growth limit (yet)"""
class AsyncConfigCache:
    """Class that will reduce calls to postgres as much as possible. Has no growth limit (yet)"""
    def __init__(self, table):
        self.cache = {}
        self.table = table

    @staticmethod
    def _hash_dict(dic):
        """Makes a dict hashable by turning it into a tuple of tuples"""
        values = []
        # sort the keys to make this repeatable; this allows consistency even when insertion order is different
        for k in sorted(dic):
            values.append((k, dic[k]))
        return tuple(values)

    async def query_one(self, **kwargs):
        """Query the cache for an entry matching the kwargs, then try again using the database."""
        query_hash = self._hash_dict(kwargs)
        if query_hash not in self.cache:
            self.cache[query_hash] = await self.table.select_one(**kwargs)
        return self.cache[query_hash]

    async def query_all(self, **kwargs):
        """Query the cache for all entries matching the kwargs, then try again using the database."""
        query_hash = self._hash_dict(kwargs)
        if query_hash not in self.cache:
            self.cache[query_hash] = await self.table.select(**kwargs)
        return self.cache[query_hash]

    def invalidate_entry(self, **kwargs):
        """Removes an entry from the cache if it exists - used to mark changed data."""
        query_hash = self._hash_dict(kwargs)
        if query_hash in self.cache:
            del self.cache[query_hash]
