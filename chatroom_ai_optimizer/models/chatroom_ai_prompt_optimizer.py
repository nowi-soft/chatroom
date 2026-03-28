import json
import logging
import re

from odoo import fields, models

_logger = logging.getLogger(__name__)


class ChatroomAIPromptOptimizer(models.Model):
    _name = "chatroom.ai.prompt.optimizer"
    _description = "AI Prompt Auto-Optimizer"
    _order = "name"

    name = fields.Char(
        required=True,
        default="Prompt Optimizer",
    )
    active = fields.Boolean(default=True)

    agent_id = fields.Many2one(
        "chatroom.ai.agent",
        required=True,
        ondelete="cascade",
        index=True,
    )

    last_optimization_date = fields.Datetime(
        readonly=True,
    )

    test_scenarios_count = fields.Integer(
        default=10,
        help="Number of simulated conversations to test each prompt version",
    )
    evaluator_temperature = fields.Float(
        default=0.7,
        help="Temperature for the evaluator AI (0.0-1.0)",
    )
    optimizer_temperature = fields.Float(
        default=0.3,
        help="Temperature for the optimizer AI (0.0-1.0)",
    )

    max_optimization_attempts = fields.Integer(
        default=3,
        help="Maximum number of attempts to generate an improved prompt per run",
    )

    test_scenario_prompts = fields.Text(
        help="Custom scenarios to test (one per line). Leave empty for auto-generated",
    )

    total_optimizations = fields.Integer(
        readonly=True,
    )
    total_improvements = fields.Integer(
        readonly=True,
        help="Number of times a new prompt performed better",
    )

    run_ids = fields.One2many(
        "chatroom.ai.optimization.run",
        "optimizer_id",
    )

    def _clamp_temperature(self, value, default=0.3):
        try:
            temp = float(value)
        except (TypeError, ValueError):
            return default
        return max(0.0, min(1.0, temp))

    def _simulation_turns(self):
        # Keep cost bounded while still testing a realistic conversation flow.
        return 3

    def _normalize_scenarios(self, scenarios):
        normalized = []
        seen = set()

        for scenario in scenarios or []:
            if not scenario:
                continue
            text = " ".join(str(scenario).split())
            # Avoid trivial one-word prompts like "Hola" that add little signal.
            if len(text) < 18 or len(text.split()) < 4:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(text)

        return normalized

    def _default_scenarios(self):
        return [
            (
                "Hola, quiero saber precio y disponibilidad de la "
                "Honda XR150L para esta semana."
            ),
            (
                "Estoy enojado porque no me respondieron ayer; "
                "necesito confirmar stock hoy mismo."
            ),
            (
                "Quiero financiar una Wave 110S, ¿qué anticipo piden "
                "y en cuántas cuotas puedo pagar?"
            ),
            (
                "Estoy entre una XR150L y una GLH150, "
                "¿cuál me conviene para delivery intenso?"
            ),
            "Necesito test ride el sábado y, si me cierra, señar en el momento.",
            (
                "Solo quería consultar colores disponibles de la Navi, "
                "todavía no decido compra."
            ),
            (
                "Tengo presupuesto ajustado: ¿qué opción usada "
                "o plan de financiación recomiendan?"
            ),
            (
                "Me confirmaron interés en compra este mes, "
                "¿pueden llamarme hoy por la tarde?"
            ),
            "Necesito un cuatriciclo para trabajo rural urgente este fin de semana.",
            "¿Hacen toma de usados? Tengo una moto para entregar en parte de pago.",
        ]

    def _extract_json_object(self, text):
        if not text:
            raise ValueError("Empty evaluation response")

        cleaned = text.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0]
        elif "```" in cleaned:
            cleaned = cleaned.split("```", 1)[1].split("```", 1)[0]

        cleaned = cleaned.strip()

        # Fast path when the content is already a plain JSON object.
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed

        raise ValueError("Evaluation response is not a JSON object")

    def _extract_json_object_fallback(self, text):
        # Fallback extractor when the model wraps JSON with extra text.
        match = re.search(r"\{[\s\S]*\}", text or "")
        if not match:
            raise ValueError("No JSON object found in evaluator response")
        parsed = json.loads(match.group(0))
        if not isinstance(parsed, dict):
            raise ValueError("Extracted JSON is not an object")
        return parsed

    def _serialize_detailed_results(self, detailed_results):
        compact = []
        for item in detailed_results or []:
            compact.append(
                {
                    "scenario_number": item.get("scenario_number"),
                    "scenario": item.get("scenario"),
                    "quality_score": item.get("quality_score"),
                    "appropriate": item.get("appropriate"),
                    "helpful": item.get("helpful"),
                    "turns_completed": item.get("turns_completed"),
                    "notes": item.get("notes"),
                }
            )
        return compact

    def _heuristic_evaluation(self, agent_response, transcript=None):
        text = (agent_response or "").strip()
        lower = text.lower()

        score = 5.0
        if len(text) >= 60:
            score += 1.0
        if "?" in text:
            score += 0.8
        if any(token in lower for token in ["gracias", "perfecto", "entiendo"]):
            score += 0.4
        if any(token in lower for token in ["stock", "precio", "financi", "test ride"]):
            score += 0.6

        score = max(3.0, min(8.0, score))

        return {
            "quality_score": round(score, 2),
            "appropriate": True,
            "helpful": bool(text),
            "notes": (
                "Heuristic fallback used: evaluator returned non-parseable output."
            ),
        }

    def action_generate_test_scenarios(self):
        self.ensure_one()

        self.with_delay(
            description=f"Generating test scenarios for {self.agent_id.name}",
            priority=5,
        ).generate_scenarios_background()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Scenario Generation Started",
                "message": (
                    f"Generating test scenarios for {self.agent_id.name} in "
                    "background. Check back in a moment."
                ),
                "type": "success",
                "sticky": False,
            },
        }

    def generate_scenarios_background(self):
        self.ensure_one()
        scenarios = self._generate_test_scenarios()
        self.test_scenario_prompts = "\n".join(scenarios)

    def action_run_optimization(self):
        self.ensure_one()

        self.with_delay(
            description=f"Optimizing prompt for {self.agent_id.name}",
            priority=5,
        ).run_optimization_cycle()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Optimization Started",
                "message": (
                    f"Optimization for {self.agent_id.name} is running in "
                    "background. Check results in a few minutes."
                ),
                "type": "success",
                "sticky": False,
                "next": {
                    "type": "ir.actions.act_window_close",
                },
            },
        }

    def run_optimization_cycle(self):
        self.ensure_one()

        run = self.env["chatroom.ai.optimization.run"].create(
            {
                "optimizer_id": self.id,
                "state": "running",
                "start_date": fields.Datetime.now(),
            }
        )

        try:
            scenarios = self._generate_test_scenarios()
            run.write({"test_scenarios": json.dumps({"scenarios": scenarios})})

            current_results = self._run_simulation(
                scenarios, self.agent_id.system_prompt
            )
            best_results = current_results

            run.write(
                {
                    "current_prompt": self.agent_id.system_prompt,
                    "current_score": current_results["overall_score"],
                    "conversations_tested": len(scenarios),
                }
            )

            original_prompt = self.agent_id.system_prompt
            best_prompt = original_prompt
            best_score = current_results["overall_score"]
            active_prompt = original_prompt
            active_results = current_results
            attempts_history = []

            for attempt in range(1, self.max_optimization_attempts + 1):
                analysis = self._analyze_performance(active_results)

                learning_context = ""
                if attempts_history:
                    learning_context = (
                        "\n\n=== PREVIOUS ATTEMPTS (LEARN FROM THESE) ===\n"
                    )
                    for i, hist in enumerate(attempts_history, 1):
                        learning_context += f"\nAttempt {i}:\n"
                        learning_context += (
                            f"Score: {hist['score']:.2f} "
                            f"(Change: {hist['improvement']:+.2f})\n"
                        )
                        learning_context += f"What went wrong: {hist['why_failed']}\n"
                        learning_context += (
                            f"Prompt tried:\n{hist['prompt'][:300]}...\n"
                        )
                        learning_context += "-" * 50 + "\n"

                improved_prompt = self._generate_improved_prompt(
                    current_prompt=active_prompt,
                    analysis=analysis,
                    current_results=active_results,
                    learning_context=learning_context,
                    attempt_number=attempt,
                )

                if not improved_prompt or not improved_prompt.strip():
                    break

                improved_results = self._run_simulation(scenarios, improved_prompt)
                improved_score = improved_results["overall_score"]
                improvement = improved_score - active_results["overall_score"]
                is_attempt_better = improved_score > active_results["overall_score"]

                if improved_score > best_score:
                    best_prompt = improved_prompt
                    best_score = improved_score
                    best_results = improved_results

                if is_attempt_better:
                    active_prompt = improved_prompt
                    active_results = improved_results
                    attempts_history.append(
                        {
                            "prompt": improved_prompt,
                            "score": improved_score,
                            "improvement": improvement,
                            "status": "accepted",
                            "why_failed": "",
                        }
                    )
                else:
                    why_failed = self._analyze_why_attempt_failed(
                        current_results=active_results,
                        improved_results=improved_results,
                        analysis=analysis,
                    )

                    attempts_history.append(
                        {
                            "prompt": improved_prompt,
                            "score": improved_score,
                            "improvement": improvement,
                            "status": "rejected",
                            "why_failed": why_failed,
                        }
                    )

            is_better = best_score > current_results["overall_score"]
            improvement = best_score - current_results["overall_score"]

            changes_summary = self._generate_changes_summary(
                original_prompt, best_prompt
            )

            attempts_summary = (
                f"\n\n=== OPTIMIZATION ATTEMPTS: {len(attempts_history)} ===\n"
            )
            for i, hist in enumerate(attempts_history, 1):
                status = hist.get("status", "rejected").upper()
                attempts_summary += (
                    f"\nAttempt {i}: Score {hist['score']:.2f} "
                    f"({hist['improvement']:+.2f}) - {status}\n"
                )
                if hist.get("why_failed"):
                    attempts_summary += f"Reason: {hist['why_failed']}\n"
            attempts_summary += (
                f"\nFinal: Score {best_score:.2f} ({improvement:+.2f}) - "
                f"{'ACCEPTED' if is_better else 'NO IMPROVEMENT'}\n"
            )

            result_status = "improved" if is_better else "no_improvement"

            run.write(
                {
                    "improved_prompt": best_prompt,
                    "new_score": best_score,
                    "improvement": improvement,
                    "test_scenarios": json.dumps(
                        {
                            "scenarios": scenarios,
                            "current_results": self._serialize_detailed_results(
                                current_results.get("detailed_results", [])
                            ),
                            "best_results": self._serialize_detailed_results(
                                best_results.get("detailed_results", [])
                            ),
                        }
                    ),
                    "state": "completed",
                    "end_date": fields.Datetime.now(),
                    "result": result_status,
                    "analysis_notes": (
                        f"{analysis}\n\nCHANGES:\n{changes_summary}{attempts_summary}"
                    ),
                }
            )

            self.write(
                {
                    "total_optimizations": self.total_optimizations + 1,
                    "total_improvements": self.total_improvements
                    + (1 if is_better else 0),
                    "last_optimization_date": fields.Datetime.now(),
                }
            )

            self.agent_id.provider_id.sudo().write(
                {
                    "last_request_date": fields.Datetime.now(),
                }
            )

            return {
                "current_score": current_results["overall_score"],
                "new_score": best_score,
                "improvement": improvement,
                "is_better": is_better,
            }

        except Exception as e:
            run.write(
                {
                    "state": "failed",
                    "end_date": fields.Datetime.now(),
                    "error_message": str(e),
                }
            )
            raise

    def _generate_test_scenarios(self):  # noqa: C901
        self.ensure_one()

        if self.test_scenario_prompts:
            scenarios = [
                line.strip()
                for line in self.test_scenario_prompts.split("\n")
                if line.strip()
            ]
            normalized = self._normalize_scenarios(scenarios)
            if len(normalized) < self.test_scenarios_count:
                fallback = self._normalize_scenarios(self._default_scenarios())
                for item in fallback:
                    if len(normalized) >= self.test_scenarios_count:
                        break
                    if item.lower() not in {s.lower() for s in normalized}:
                        normalized.append(item)
            return normalized[: self.test_scenarios_count]

        knowledge_context = ""
        if self.agent_id.knowledge_ids:
            knowledge_context = "\n\n=== KNOWLEDGE BASE (FULL CONTENT) ===\n"
            for knowledge in self.agent_id.knowledge_ids:
                content = knowledge.get_formatted_content()
                knowledge_context += f"\n{knowledge.name}:\n{content}\n{'-' * 50}\n"

        tools_context = ""
        if self.agent_id.tool_ids:
            tools_context = "\n\n=== AVAILABLE TOOLS ===\n"
            for tool in self.agent_id.tool_ids:
                tools_context += f"\n• {tool.name}\n  Description: {tool.description}\n"

        current_prompt = self.agent_id.system_prompt or ""

        generation_prompt = (
            f"""You are a QA specialist creating test scenarios for an AI """
            f"""customer service agent.

=== AGENT INFORMATION ===
Name: {self.agent_id.name}

System Prompt:
{current_prompt}
{tools_context}{knowledge_context}

=== YOUR TASK ===
Generate {self.test_scenarios_count} diverse, realistic customer messages """
            f"""to thoroughly test this agent.

REQUIREMENTS:
- Each message: 1-3 sentences, max 150 words
- Natural conversational Spanish
- Test DIFFERENT aspects based on the knowledge base and tools above
- Include various scenarios:
  * Questions about specific topics in the knowledge base
  * Requests that require using the available tools
  * Simple questions and complex multi-part questions
  * Different emotions: neutral, happy, frustrated, urgent
  * Edge cases (off-topic, unclear, etc.)

EXAMPLES:
"Hola, necesito información sobre [topic from KB]"
"Estoy enojado porque [issue]"
"¿Pueden ayudarme con [specific request]?"
"Necesito [service] urgente"

Return ONLY a JSON array of strings: ["message 1", "message 2", ...]
"""
        )

        try:
            provider_max_tokens = getattr(self.agent_id.provider_id, "max_tokens", None)
            max_tokens_to_use = provider_max_tokens if provider_max_tokens else 8000
            generation_temperature = self._clamp_temperature(
                self.optimizer_temperature, default=0.7
            )

            result = self.agent_id.provider_id.generate_completion(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You respond ONLY with valid JSON arrays. Nothing else."
                        ),
                    },
                    {"role": "user", "content": generation_prompt},
                ],
                temperature=generation_temperature,
                max_tokens=max_tokens_to_use,
            )

            content = result.get("content", "")
            usage = result.get("usage", {})

            if not content or not content.strip():
                raise ValueError(
                    f"AI returned empty response. Completion tokens: "
                    f"{usage.get('completion_tokens', 0)}"
                )

            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            scenarios = json.loads(content.strip())

            if not isinstance(scenarios, list):
                raise ValueError("Expected JSON array")

            if len(scenarios) == 0:
                raise ValueError("Empty scenarios array")

            normalized_scenarios = self._normalize_scenarios(scenarios)
            if len(normalized_scenarios) < self.test_scenarios_count:
                fallback = self._normalize_scenarios(self._default_scenarios())
                for item in fallback:
                    if len(normalized_scenarios) >= self.test_scenarios_count:
                        break
                    if item.lower() not in {s.lower() for s in normalized_scenarios}:
                        normalized_scenarios.append(item)

            return normalized_scenarios[: self.test_scenarios_count]

        except Exception:
            fallback = self._normalize_scenarios(self._default_scenarios())
            return fallback[: self.test_scenarios_count]

    def _run_simulation(self, scenarios, system_prompt):
        self.ensure_one()

        results = []
        for i, scenario in enumerate(scenarios):
            try:
                test_result = self._test_single_scenario_sync(
                    scenario=scenario,
                    scenario_number=i + 1,
                    system_prompt=system_prompt,
                )
                test_result.update(
                    {
                        "scenario_number": i + 1,
                        "scenario": scenario,
                    }
                )
                results.append(test_result)

            except Exception as e:
                results.append(
                    {
                        "quality_score": 0.0,
                        "appropriate": False,
                        "helpful": False,
                        "notes": f"Test failed: {str(e)}",
                        "scenario_number": i + 1,
                        "scenario": scenario,
                    }
                )

        quality_scores = [r["quality_score"] for r in results]
        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0

        appropriate_count = sum(1 for r in results if r.get("appropriate", False))
        helpful_count = sum(1 for r in results if r.get("helpful", False))

        success_rate_pct = (helpful_count / len(results) * 100) if results else 0
        tool_accuracy_pct = (appropriate_count / len(results) * 100) if results else 0

        overall_score = (
            avg_quality * 10 * 0.5 + success_rate_pct * 0.3 + tool_accuracy_pct * 0.2
        )

        return {
            "overall_score": overall_score,
            "avg_quality": avg_quality,
            "success_rate": success_rate_pct,
            "tool_accuracy": tool_accuracy_pct,
            "conversations_tested": len(results),
            "detailed_results": results,
        }

    def _test_single_scenario_sync(self, scenario, scenario_number, system_prompt):
        self.ensure_one()

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": scenario},
            ]
            transcript = [
                {
                    "role": "user",
                    "content": scenario,
                }
            ]

            last_response_text = ""
            for turn in range(1, self._simulation_turns() + 1):
                agent_response = self.agent_id.provider_id.generate_completion(
                    messages=messages,
                    model=self.agent_id.model or None,
                    temperature=self.agent_id.temperature or None,
                )
                response_text = (agent_response.get("content") or "").strip()
                if not response_text:
                    response_text = "No response generated"

                messages.append({"role": "assistant", "content": response_text})
                transcript.append({"role": "assistant", "content": response_text})
                last_response_text = response_text

                if turn >= self._simulation_turns():
                    break

                user_follow_up = self._generate_customer_followup(
                    scenario=scenario,
                    transcript=transcript,
                    turn_number=turn,
                )
                if not user_follow_up:
                    break

                messages.append({"role": "user", "content": user_follow_up})
                transcript.append({"role": "user", "content": user_follow_up})

            evaluation = self._evaluate_response(
                user_message=scenario,
                agent_response=last_response_text,
                system_prompt=system_prompt,
                transcript=transcript,
            )

            return {
                "quality_score": evaluation["quality_score"],
                "appropriate": evaluation.get("appropriate", True),
                "helpful": evaluation.get("helpful", True),
                "notes": evaluation.get("notes", ""),
                "turns_completed": len(transcript),
            }

        except Exception as e:
            return {
                "quality_score": 0.0,
                "appropriate": False,
                "helpful": False,
                "notes": f"Test failed: {str(e)}",
            }

    def _generate_customer_followup(self, scenario, transcript, turn_number):
        self.ensure_one()

        followup_temperature = self._clamp_temperature(
            self.evaluator_temperature, default=0.7
        )

        transcript_text = "\n".join(
            f"{entry['role'].upper()}: {entry['content']}" for entry in transcript
        )

        followup_prompt = f"""Simulate the SAME customer continuing the conversation.

Original scenario:
{scenario}

Conversation so far:
{transcript_text}

Generate exactly ONE realistic next customer message in Spanish.
Rules:
- 1 short message (max 35 words)
- Keep context continuity
- Add useful detail when asked by the agent
- Sound natural for WhatsApp/Telegram
- Return plain text only
"""

        try:
            provider_max_tokens = getattr(self.agent_id.provider_id, "max_tokens", None)
            max_tokens_to_use = (
                min(provider_max_tokens, 250) if provider_max_tokens else 120
            )

            result = self.agent_id.provider_id.generate_completion(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You simulate a customer in a chat. Respond with one short "
                            "message only."
                        ),
                    },
                    {"role": "user", "content": followup_prompt},
                ],
                temperature=followup_temperature,
                max_tokens=max_tokens_to_use,
            )

            followup = (result.get("content") or "").strip()
            if followup:
                return followup

        except Exception as error:
            _logger.debug("Follow-up generation failed: %s", error)

        fallback_turns = {
            1: (
                "Perfecto, estoy en Mendoza y quiero resolverlo hoy. "
                "Si te sirve me contactan por WhatsApp."
            ),
            2: (
                "Dale, si hay stock avanzo. "
                "Tambien quiero saber opciones de financiacion."
            ),
        }
        return fallback_turns.get(turn_number, "Gracias, quedo atento.")

    def _evaluate_response(
        self, user_message, agent_response, system_prompt, transcript=None
    ):
        self.ensure_one()

        transcript_text = ""
        if transcript:
            transcript_text = "\n\nFULL CONVERSATION:\n" + "\n".join(
                f"{entry['role'].upper()}: {entry['content']}" for entry in transcript
            )

        evaluation_prompt = (
            "You are evaluating an AI customer service agent's response.\n\n"
            f"USER MESSAGE:\n{user_message}\n\n"
            f"AGENT RESPONSE:\n{agent_response}\n\n"
            f"{transcript_text}\n\n"
            "Rate the response quality from 1 to 10 where:\n"
            "- 1-3: Poor (unhelpful, irrelevant, or rude)\n"
            "- 4-6: Acceptable (basic help but could be better)\n"
            "- 7-9: Good (helpful, professional, addresses the question)\n"
            "- 10: Excellent (perfect response)\n\n"
            "IMPORTANT:\n"
            "- Always give a score between 1 and 10\n"
            "- Be strict about conversation continuity and goal progression\n"
            "- Penalize if the agent ignores context, asks redundant questions, "
            "or misses clear next steps\n"
            "- Reward if the agent advances naturally toward qualification "
            "and resolution\n\n"
            "Return ONLY valid JSON with this exact format:\n"
            "{\n"
            '  "quality_score": 7.5,\n'
            '  "appropriate": true,\n'
            '  "helpful": true,\n'
            '  "notes": "Brief reason for the score"\n'
            "}"
        )

        try:
            provider_max_tokens = getattr(self.agent_id.provider_id, "max_tokens", None)
            max_tokens_to_use = (
                min(provider_max_tokens, 1000) if provider_max_tokens else 500
            )
            evaluation_temperature = self._clamp_temperature(
                self.evaluator_temperature, default=0.3
            )

            raw_content = ""
            last_error = ""
            for attempt in range(2):
                attempt_temperature = evaluation_temperature if attempt == 0 else 0.0
                result = self.agent_id.provider_id.generate_completion(
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are an evaluator. Respond with exactly one valid "
                                "JSON object and nothing else."
                            ),
                        },
                        {"role": "user", "content": evaluation_prompt},
                    ],
                    temperature=attempt_temperature,
                    max_tokens=max_tokens_to_use,
                )

                raw_content = result.get("content", "")
                try:
                    evaluation = self._extract_json_object(raw_content)
                except Exception:
                    try:
                        evaluation = self._extract_json_object_fallback(raw_content)
                    except Exception as parse_error:
                        last_error = str(parse_error)
                        continue

                quality_score = float(evaluation.get("quality_score", 5))
                if quality_score < 1 or quality_score > 10:
                    quality_score = 5.0

                notes = evaluation.get("notes", "") or ""
                if attempt > 0:
                    notes = f"{notes} [Evaluator retry #{attempt + 1}]".strip()

                return {
                    "quality_score": quality_score,
                    "appropriate": evaluation.get("appropriate", True),
                    "helpful": evaluation.get("helpful", True),
                    "notes": notes,
                }

            raw_excerpt = (raw_content or "").replace("\n", " ")[:180]
            heuristic = self._heuristic_evaluation(
                agent_response=agent_response,
                transcript=transcript,
            )
            heuristic["notes"] = (
                f"{heuristic['notes']} Parse error: {last_error or 'unknown'}; "
                f"raw='{raw_excerpt}'"
            )
            return heuristic

        except Exception as e:
            error_msg = str(e)
            if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                return {
                    "quality_score": 6.0,
                    "appropriate": True,
                    "helpful": True,
                    "notes": "Evaluation timed out - using neutral score",
                }

            return {
                "quality_score": 5.0,
                "appropriate": True,
                "helpful": True,
                "notes": f"Evaluation error: {error_msg[:100]}",
            }

    def _analyze_performance(self, results):
        self.ensure_one()

        detailed_results = results.get("detailed_results", [])

        all_notes = "\n".join(
            [f"- {r['notes']}" for r in detailed_results if r.get("notes")]
        )

        analysis_prompt = f"""You are an AI prompt optimization expert.

CURRENT PERFORMANCE:
- Overall Score: {results["overall_score"]:.2f}/100
- Average Quality: {results["avg_quality"]:.2f}/10
- Success Rate: {results["success_rate"]:.2f}%
- Tool Accuracy: {results["tool_accuracy"]:.2f}%

EVALUATION NOTES FROM TESTS:
{all_notes}

Analyze these results and identify:
1. Top 3 problems with the current prompt
2. Specific areas for improvement
3. What the prompt is doing well (to preserve)

Be concise and actionable. 2-3 sentences per point.
"""

        try:
            analysis_temperature = self._clamp_temperature(
                self.optimizer_temperature, default=0.3
            )
            result = self.agent_id.provider_id.generate_completion(
                messages=[{"role": "user", "content": analysis_prompt}],
                temperature=analysis_temperature,
            )

            return result.get("content", "No analysis available")

        except Exception as e:
            return f"Analysis error: {str(e)}"

    def _generate_improved_prompt(
        self,
        current_prompt,
        analysis,
        current_results,
        learning_context="",
        attempt_number=1,
    ):
        self.ensure_one()

        optimization_prompt = (
            f"""You are an expert AI prompt engineer. Your task is to improve a """
            f"""system prompt based on performance analysis.

CURRENT SYSTEM PROMPT:
{current_prompt}

PERFORMANCE ANALYSIS:
{analysis}

CURRENT SCORES:
- Overall: {current_results["overall_score"]:.2f}/100
- Quality: {current_results["avg_quality"]:.2f}/10
- Success Rate: {current_results["success_rate"]:.2f}%

{learning_context}

=== ATTEMPT {attempt_number} OF {self.max_optimization_attempts} ===

TASK: Generate an improved system prompt that:
1. Fixes the identified problems from the analysis
2. {
                "LEARNS from previous failed attempts above - "
                "DO NOT repeat the same mistakes"
                if learning_context
                else "Addresses the weaknesses identified"
            }
3. Maintains the agent's personality and core purpose
4. Adds specific instructions to address weaknesses
5. Keeps the same structure and tone

CRITICAL INSTRUCTIONS:
- Return ONLY the new system prompt text
- Do NOT add explanations, comments, or markdown
- Do NOT use JSON format
- Start directly with the prompt content
- Make sure the prompt is at least 200 characters long
- If you cannot improve it significantly, return the original prompt

Begin your response now:
"""
        )

        try:
            provider_max_tokens = getattr(self.agent_id.provider_id, "max_tokens", None)
            max_tokens_to_use = provider_max_tokens if provider_max_tokens else 8000
            optimizer_temperature = self._clamp_temperature(
                self.optimizer_temperature, default=0.7
            )

            result = self.agent_id.provider_id.generate_completion(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a helpful assistant that generates improved AI "
                            "system prompts. You always respond with the prompt text "
                            "only, never with explanations."
                        ),
                    },
                    {"role": "user", "content": optimization_prompt},
                ],
                temperature=optimizer_temperature,
                max_tokens=max_tokens_to_use,
            )

            improved_prompt = result.get("content", "")

            if improved_prompt.startswith("```"):
                lines = improved_prompt.split("\n")
                improved_prompt = "\n".join(lines[1:-1])

            improved_prompt = improved_prompt.strip()

            if not improved_prompt or len(improved_prompt) < 50:
                return current_prompt

            return improved_prompt

        except Exception as e:
            if not current_prompt:
                raise ValueError(
                    "Failed to generate improved prompt and current prompt is empty"
                ) from e
            return current_prompt

    def _analyze_why_attempt_failed(self, current_results, improved_results, analysis):
        self.ensure_one()

        failure_prompt = (
            f"""You are analyzing why an AI prompt optimization attempt FAILED """
            f"""(made things worse).

ORIGINAL PERFORMANCE:
- Overall Score: {current_results["overall_score"]:.2f}/100
- Quality: {current_results["avg_quality"]:.2f}/10
- Success Rate: {current_results["success_rate"]:.2f}%

NEW (WORSE) PERFORMANCE:
- Overall Score: {improved_results["overall_score"]:.2f}/100
- Quality: {improved_results["avg_quality"]:.2f}/10
- Success Rate: {improved_results["success_rate"]:.2f}%

ORIGINAL ANALYSIS:
{analysis}

In 2-3 sentences, explain:
1. What specific aspect got worse (quality, success rate, or tool accuracy)?
2. What likely caused this degradation?
3. What should be avoided in the next attempt?

Be direct and actionable.
"""
        )

        try:
            analysis_temperature = self._clamp_temperature(
                self.evaluator_temperature, default=0.3
            )
            result = self.agent_id.provider_id.generate_completion(
                messages=[{"role": "user", "content": failure_prompt}],
                temperature=analysis_temperature,
                max_tokens=300,
            )

            content = result.get("content", "").strip()
            if not content:
                raise ValueError("Empty response from AI")

            return content

        except Exception:
            quality_diff = (
                improved_results["avg_quality"] - current_results["avg_quality"]
            )
            success_diff = (
                improved_results["success_rate"] - current_results["success_rate"]
            )

            if quality_diff < -0.5:
                return (
                    "Quality degraded significantly. The new prompt likely made "
                    "responses less helpful or relevant."
                )
            elif success_diff < -5:
                return (
                    "Success rate dropped. The new prompt may have made the agent "
                    "less effective at completing tasks."
                )
            else:
                return (
                    "Overall performance decreased. The changes did not address "
                    "the core issues."
                )

    def _generate_changes_summary(self, old_prompt, new_prompt):
        self.ensure_one()

        summary_prompt = (
            f"""Compare these two prompts and summarize the key changes in """
            f"""2-3 bullet points.

OLD PROMPT:
{old_prompt[:500]}...

NEW PROMPT:
{new_prompt[:500]}...

Focus on meaningful differences, not just wording. Be concise.
"""
        )

        try:
            summary_temperature = self._clamp_temperature(
                self.evaluator_temperature, default=0.3
            )
            result = self.agent_id.provider_id.generate_completion(
                messages=[{"role": "user", "content": summary_prompt}],
                temperature=summary_temperature,
            )

            return result.get("content", "Changes not summarized")

        except Exception as e:
            return f"Could not generate summary: {str(e)}"
