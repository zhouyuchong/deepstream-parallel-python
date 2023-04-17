import abc

class InferBin(abc.ABC):
    def __ini__():
        pass

    @abc.abstractmethod
    def make_elements(self):
        ...

    @abc.abstractmethod
    def link_elements(self):
        ...

    @abc.abstractmethod
    def add_new_source(self, padname):
        ...

    @abc.abstractmethod
    def release_streammux(self):
        ...
    