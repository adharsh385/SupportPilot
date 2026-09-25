from rag.pipeline import run_rag_pipeline


class DiagnosisAgent:

    def run(self, ticket):

        return {

            "agent":
                "Diagnosis Agent",

            "status":
                "Active",

            "category":
                ticket.get(
                    "category",
                    "Unknown"
                ),

            "severity":
                ticket.get(
                    "severity",
                    "Unknown"
                ),

            "priority":
                ticket.get(
                    "priority",
                    "Unknown"
                ),

            "message":
                "Ticket diagnosis completed."
        }


class RetrievalAgent:

    def run(self, ticket):

        result = run_rag_pipeline(
            ticket
        )

        result["agent"] = (
            "Retrieval Agent"
        )

        return result


class ResolutionAgent:

    def run(
        self,
        ticket,
        retrieval_result
    ):

        return {

            "agent":
                "Resolution Agent",

            "status":
                "Active",

            "resolution":
                retrieval_result["resolution"],

            "steps":
                retrieval_result[
                    "resolution_steps"
                ],

            "message":
                "Troubleshooting resolution generated."
        }


class ValidationAgent:

    def run(
        self,
        ticket,
        resolution_result
    ):

        steps = resolution_result.get(
            "steps",
            []
        )

        if len(steps) > 0:

            return {

                "agent":
                    "Validation Agent",

                "status":
                    "Completed",

                "valid":
                    True,

                "message":
                    "Resolution contains valid knowledge-base steps."
            }

        return {

            "agent":
                "Validation Agent",

            "status":
                "Needs Review",

            "valid":
                False,

            "message":
                "Resolution requires manual review."
        }


class EscalationAgent:

    def run(
        self,
        ticket,
        validation_result
    ):

        severity = ticket.get(
            "severity",
            "Low"
        )

        if severity == "Critical":

            return {

                "agent":
                    "Escalation Agent",

                "status":
                    "Active",

                "escalate":
                    True,

                "message":
                    "Critical ticket escalated."
            }

        if not validation_result["valid"]:

            return {

                "agent":
                    "Escalation Agent",

                "status":
                    "Active",

                "escalate":
                    True,

                "message":
                    "Ticket requires manual review."
            }

        return {

            "agent":
                "Escalation Agent",

            "status":
                "Standby",

            "escalate":
                False,

            "message":
                "No escalation required."
        }


class SupportPilot:

    def __init__(self):

        self.diagnosis_agent = (
            DiagnosisAgent()
        )

        self.retrieval_agent = (
            RetrievalAgent()
        )

        self.resolution_agent = (
            ResolutionAgent()
        )

        self.validation_agent = (
            ValidationAgent()
        )

        self.escalation_agent = (
            EscalationAgent()
        )

    def process(self, ticket):

        workflow = []

        # -----------------------------------------
        # 1. DIAGNOSIS
        # -----------------------------------------

        diagnosis = (
            self.diagnosis_agent.run(
                ticket
            )
        )

        workflow.append({

            "agent":
                "Diagnosis",

            "status":
                diagnosis["status"]
        })

        # -----------------------------------------
        # 2. RETRIEVAL
        # -----------------------------------------

        retrieval = (
            self.retrieval_agent.run(
                ticket
            )
        )

        workflow.append({

            "agent":
                "Retrieval",

            "status":
                "Active"
        })

        # -----------------------------------------
        # 3. RESOLUTION
        # -----------------------------------------

        resolution = (
            self.resolution_agent.run(
                ticket,
                retrieval
            )
        )

        workflow.append({

            "agent":
                "Resolution",

            "status":
                resolution["status"]
        })

        # -----------------------------------------
        # 4. VALIDATION
        # -----------------------------------------

        validation = (
            self.validation_agent.run(
                ticket,
                resolution
            )
        )

        workflow.append({

            "agent":
                "Validation",

            "status":
                validation["status"]
        })

        # -----------------------------------------
        # 5. ESCALATION
        # -----------------------------------------

        escalation = (
            self.escalation_agent.run(
                ticket,
                validation
            )
        )

        workflow.append({

            "agent":
                "Escalation",

            "status":
                escalation["status"]
        })

        return {

            "diagnosis":
                diagnosis,

            "retrieval":
                retrieval,

            "resolution":
                resolution,

            "validation":
                validation,

            "escalation":
                escalation,

            "workflow":
                workflow
        }