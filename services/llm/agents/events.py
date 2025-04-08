from llama_index.core.workflow import Event

class QueryEvent(Event):
    prompt: str
    index_ids: list = None
    
    
class ReviewEvent(Event):
    answer: str

class ReviewResults(Event):
    review: str

class RewriteEvent(Event):
    review: str

class WriteEvent(Event):
    pass