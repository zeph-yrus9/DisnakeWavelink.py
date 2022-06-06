# noinspection PyPep8Naming
class classproperty:
    def __init__(self, fget) -> None:
        self.fget = fget

    def __get__(self, instance, owner):
        return self.fget(owner)

    def __set__(self, instance, value) -> None:
        raise AttributeError('cannot set attribute')
