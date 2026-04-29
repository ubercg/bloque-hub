from ai_memory.graph.code_graph_builder import CodeGraphBuilder

builder = CodeGraphBuilder(".")
builder.build()
builder.save()