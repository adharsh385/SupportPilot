from data.rag.analyzer import analyze_ticket

from data.rag.retriever import KnowledgeRetriever

from data.rag.generator import (
    build_context,
    generate_resolution
)


def run_rag_pipeline(ticket):

    workflow = {

        "ticket_analysis":
            "processing",

        "knowledge_retrieval":
            "waiting",

        "context_augmentation":
            "waiting",

        "response_generation":
            "waiting"

    }

    analysis = analyze_ticket(
        ticket
    )

    workflow[
        "ticket_analysis"
    ] = "completed"

    retriever = KnowledgeRetriever()

    results = retriever.search(
        analysis["query"],
        top_k=3
    )

    workflow[
        "knowledge_retrieval"
    ] = "completed"

    context = build_context(
        results
    )

    workflow[
        "context_augmentation"
    ] = "completed"

    generated = generate_resolution(
        ticket,
        results
    )

    workflow[
        "response_generation"
    ] = "completed"

    return {

        "analysis":
            analysis,

        "retrieved_documents":
            results,

        "context":
            context,

        "resolution":
            generated["text"],

        "resolution_steps":
            generated["steps"],

        "resolution_status":
            generated["status"],

        "workflow":
            workflow

    }