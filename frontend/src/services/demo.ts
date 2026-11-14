import { parseContract } from './contractCheck.ts';
// Explicit illustrative fixture. Never an API fallback or backend authorization.
export const demoScan = parseContract('Scan', {
  "schema_version": "cascaderouter.scan.v1",
  "analysis_id": "analysis_5dca3dad3cee4697b67de955d385d92f",
  "timestamp": "2026-10-29T08:37:16.525480Z",
  "repository_path": "examples/customer_support_agent",
  "nodes": [
    {
      "file_path": "support_agent.py",
      "line_number": 14,
      "column_number": 11,
      "node_id": "llm_4d6f1d6629a81593fae3739f",
      "current_model": "meta-llama/Meta-Llama-3.1-70B-Instruct",
      "call_signature": "openai.OpenAI.chat.completions.create(...)",
      "function_name": "triage_intent",
      "model_resolution": "literal",
      "model_reference": null,
      "model_references": [],
      "prompt_resolution": "literal",
      "prompt_reference": null,
      "prompt_references": [],
      "schema_resolution": "missing",
      "schema_reference": null,
      "schema_references": [],
      "limited_schema_summary": null
    },
    {
      "file_path": "support_agent.py",
      "line_number": 28,
      "column_number": 11,
      "node_id": "llm_5e7a2b3318b72481eba2841a",
      "current_model": "meta-llama/Meta-Llama-3.1-70B-Instruct",
      "call_signature": "openai.OpenAI.chat.completions.create(...)",
      "function_name": "extract_context",
      "model_resolution": "literal",
      "model_reference": null,
      "model_references": [],
      "prompt_resolution": "literal",
      "prompt_reference": null,
      "prompt_references": [],
      "schema_resolution": "missing",
      "schema_reference": null,
      "schema_references": [],
      "limited_schema_summary": null
    },
    {
      "file_path": "support_agent.py",
      "line_number": 42,
      "column_number": 11,
      "node_id": "llm_6f8b3c4429c83592fcb3952b",
      "current_model": "meta-llama/Meta-Llama-3.1-70B-Instruct",
      "call_signature": "openai.OpenAI.chat.completions.create(...)",
      "function_name": "draft_reply",
      "model_resolution": "literal",
      "model_reference": null,
      "model_references": [],
      "prompt_resolution": "literal",
      "prompt_reference": null,
      "prompt_references": [],
      "schema_resolution": "missing",
      "schema_reference": null,
      "schema_references": [],
      "limited_schema_summary": null
    }
  ],
  "graph_edges": [
    ["llm_4d6f1d6629a81593fae3739f", "llm_5e7a2b3318b72481eba2841a"],
    ["llm_5e7a2b3318b72481eba2841a", "llm_6f8b3c4429c83592fcb3952b"]
  ],
  "scanned_files_count": 1,
  "discovered_files_count": 1,
  "total_source_bytes_read": 1420,
  "detected_framework": "OpenAI SDK",
  "data_source": "mock",
  "scan_complete": true,
  "graph_complete": true,
  "complete": true,
  "scan_diagnostics": [],
  "graph_diagnostics": []
});


export const demoJob = parseContract('Job', {
  "schema_version": "cascaderouter.benchmark.v1",
  "run_id": "run_9282aefccc1c48fba41ce9abd0ef762f",
  "status": "complete",
  "plan": {
    "schema_version": "cascaderouter.benchmark.v1",
    "analysis_id": "analysis_5dca3dad3cee4697b67de955d385d92f",
    "analysis_schema_version": "cascaderouter.scan.v1",
    "analysis_digest": "c59419b2a1f8659b866ca4cdfbd3738b8f31ae8171169e83cd31cf47ddcb4237",
    "node_ids": [
      "llm_4d6f1d6629a81593fae3739f"
    ],
    "models": [
      {
        "identifier": "local/baseline",
        "version": "v1"
      },
      {
        "identifier": "local/candidate",
        "version": "v1"
      }
    ],
    "case_set": {
      "identifier": "cases",
      "version": "v1"
    },
    "case_ids": [
      "case-one",
      "case-two"
    ],
    "evaluation_profile": {
      "identifier": "profile",
      "version": "v1"
    },
    "registry_digest": "863390a850efdedf8325d50326d9b63237f962a702df2c81844046b52d2afb65",
    "configuration_version": "zero-cost.jobs.v1",
    "configuration_digest": "dbb8023b293add83c490ed4cda87b02928cb7c2305d1ba14c83372f6bd293adb",
    "execution_digest": "5e9fd59a6e382e2efe90a2be616c588fdc592a71fdc8678289ace63bbc04f2bd",
    "provenance": "test",
    "case_set_digest": "40dbfd689fb286b9c1250babcf5a4b98f7646bdaa0a27c8d6b99a297ecd3b938",
    "evaluation_profile_digest": "090c8f81bf71faad2dd86468d39b36ac78fdd749c88163904487f6bb3c6777fa"
  },
  "created_at": "2026-10-29T08:37:16.552512Z",
  "updated_at": "2026-10-29T08:37:16.580865Z",
  "deadline_at": "2026-10-29T08:42:16.552512Z",
  "finished_at": "2026-10-29T08:37:16.580865Z",
  "idempotency_key": null,
  "progress": {
    "completed_units": 4,
    "total_units": 4
  },
  "measurements": [
    {
      "node_id": "llm_4d6f1d6629a81593fae3739f",
      "model_id": "local/baseline",
      "case_id": "case-one",
      "provenance": "test",
      "latency_ms": {
        "availability": "unavailable",
        "value": null
      },
      "input_tokens": {
        "availability": "available",
        "value": 1000000
      },
      "output_tokens": {
        "availability": "available",
        "value": 0
      },
      "cost_usd": {
        "availability": "unavailable",
        "value": null
      },
      "evaluation_status": "passed",
      "quality_score": null,
      "evaluation": {
        "status": "passed",
        "reason": "matched",
        "checks_ran": [
          "exact"
        ],
        "validation_status": "passed"
      },
      "ttft_ms": {
        "availability": "unavailable",
        "value": null
      },
      "calculated_cost": {
        "availability": "available",
        "amount_usd": "1.00",
        "reason": null,
        "pricing_reference": {
          "identifier": "test-price-baseline",
          "version": "v1"
        },
        "pricing_digest": "8882d78b9931ee62f4842fc20b7f8b5c32c7d087a412b0cf11e338d4c954c321"
      },
      "recording_id": "test-record-0",
      "evidence_digest": "8297e63178231da621f97caa9487e86fbd331b20ea13f2ef48d31b633925e2bb",
      "output_available": true
    },
    {
      "node_id": "llm_4d6f1d6629a81593fae3739f",
      "model_id": "local/baseline",
      "case_id": "case-two",
      "provenance": "test",
      "latency_ms": {
        "availability": "unavailable",
        "value": null
      },
      "input_tokens": {
        "availability": "available",
        "value": 1000000
      },
      "output_tokens": {
        "availability": "available",
        "value": 0
      },
      "cost_usd": {
        "availability": "unavailable",
        "value": null
      },
      "evaluation_status": "passed",
      "quality_score": null,
      "evaluation": {
        "status": "passed",
        "reason": "matched",
        "checks_ran": [
          "exact"
        ],
        "validation_status": "passed"
      },
      "ttft_ms": {
        "availability": "unavailable",
        "value": null
      },
      "calculated_cost": {
        "availability": "available",
        "amount_usd": "1.00",
        "reason": null,
        "pricing_reference": {
          "identifier": "test-price-baseline",
          "version": "v1"
        },
        "pricing_digest": "8882d78b9931ee62f4842fc20b7f8b5c32c7d087a412b0cf11e338d4c954c321"
      },
      "recording_id": "test-record-1",
      "evidence_digest": "b05c076b4f3eb5c32c4cd8138113125f1e434a83f62dd80f72c711bbf5d2c6ae",
      "output_available": true
    },
    {
      "node_id": "llm_4d6f1d6629a81593fae3739f",
      "model_id": "local/candidate",
      "case_id": "case-one",
      "provenance": "test",
      "latency_ms": {
        "availability": "unavailable",
        "value": null
      },
      "input_tokens": {
        "availability": "available",
        "value": 1000000
      },
      "output_tokens": {
        "availability": "available",
        "value": 0
      },
      "cost_usd": {
        "availability": "unavailable",
        "value": null
      },
      "evaluation_status": "passed",
      "quality_score": null,
      "evaluation": {
        "status": "passed",
        "reason": "matched",
        "checks_ran": [
          "exact"
        ],
        "validation_status": "passed"
      },
      "ttft_ms": {
        "availability": "unavailable",
        "value": null
      },
      "calculated_cost": {
        "availability": "available",
        "amount_usd": "0.50",
        "reason": null,
        "pricing_reference": {
          "identifier": "test-price-candidate",
          "version": "v1"
        },
        "pricing_digest": "ef428d100ea145d87c3b8d102ea30278607caaa78ec403fb4e3f4e7fd849d528"
      },
      "recording_id": "test-record-2",
      "evidence_digest": "167e67b1294d5ab15621bcc079fc37a0cc3b5bf4638c736a820caae94047eb98",
      "output_available": true
    },
    {
      "node_id": "llm_4d6f1d6629a81593fae3739f",
      "model_id": "local/candidate",
      "case_id": "case-two",
      "provenance": "test",
      "latency_ms": {
        "availability": "unavailable",
        "value": null
      },
      "input_tokens": {
        "availability": "available",
        "value": 1000000
      },
      "output_tokens": {
        "availability": "available",
        "value": 0
      },
      "cost_usd": {
        "availability": "unavailable",
        "value": null
      },
      "evaluation_status": "passed",
      "quality_score": null,
      "evaluation": {
        "status": "passed",
        "reason": "matched",
        "checks_ran": [
          "exact"
        ],
        "validation_status": "passed"
      },
      "ttft_ms": {
        "availability": "unavailable",
        "value": null
      },
      "calculated_cost": {
        "availability": "available",
        "amount_usd": "0.50",
        "reason": null,
        "pricing_reference": {
          "identifier": "test-price-candidate",
          "version": "v1"
        },
        "pricing_digest": "ef428d100ea145d87c3b8d102ea30278607caaa78ec403fb4e3f4e7fd849d528"
      },
      "recording_id": "test-record-3",
      "evidence_digest": "d04dde4d695780aaed2924f9b1859ae47355ea6ab5a432b0b0a5c7dcb354a5da",
      "output_available": true
    }
  ],
  "result": {
    "provenance": "test",
    "evaluation_status": "passed",
    "metrics": {
      "provenance": "test",
      "planned_cases": 2,
      "planned_units": 4,
      "processed_units": 4,
      "valid_recorded_outputs": 4,
      "evaluated_units": 4,
      "passed": 4,
      "failed": 0,
      "skipped": 0,
      "inconclusive": 0,
      "not_run": 0,
      "processing_complete": true,
      "evaluation_complete": true,
      "latency_ms": {
        "availability": "unavailable",
        "unit": "ms",
        "sample_count": 0,
        "minimum": null,
        "maximum": null,
        "mean": null,
        "total_tokens": null,
        "total_usd": null,
        "reason": "empty_population"
      },
      "ttft_ms": {
        "availability": "unavailable",
        "unit": "ms",
        "sample_count": 0,
        "minimum": null,
        "maximum": null,
        "mean": null,
        "total_tokens": null,
        "total_usd": null,
        "reason": "empty_population"
      },
      "input_tokens": {
        "availability": "available",
        "unit": "tokens",
        "sample_count": 4,
        "minimum": null,
        "maximum": null,
        "mean": null,
        "total_tokens": 4000000,
        "total_usd": null,
        "reason": null
      },
      "output_tokens": {
        "availability": "available",
        "unit": "tokens",
        "sample_count": 4,
        "minimum": null,
        "maximum": null,
        "mean": null,
        "total_tokens": 0,
        "total_usd": null,
        "reason": null
      },
      "cost_usd": {
        "availability": "available",
        "unit": "USD",
        "sample_count": 4,
        "minimum": null,
        "maximum": null,
        "mean": null,
        "total_tokens": null,
        "total_usd": "3.00",
        "reason": null
      }
    }
  },
  "error": null,
  "cancellation_reason": null
});

export const demoOptimization = parseContract('Optimization', {
  "result": {
    "schema_version": "cascaderouter.optimization.v1",
    "objective_version": "all-checks-then-cost.v1",
    "configuration_version": "zero-cost.optimizer.v1",
    "configuration_digest": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "run_id": "run_9282aefccc1c48fba41ce9abd0ef762f",
    "benchmark_digest": "d51e740e62587822605587c9379dde6f76a55a673d5428e0905dda3a6a2181d7",
    "plan": {
      "schema_version": "cascaderouter.benchmark.v1",
      "analysis_id": "analysis_5dca3dad3cee4697b67de955d385d92f",
      "analysis_schema_version": "cascaderouter.scan.v1",
      "analysis_digest": "c59419b2a1f8659b866ca4cdfbd3738b8f31ae8171169e83cd31cf47ddcb4237",
      "node_ids": [
        "llm_4d6f1d6629a81593fae3739f"
      ],
      "models": [
        {
          "identifier": "local/baseline",
          "version": "v1"
        },
        {
          "identifier": "local/candidate",
          "version": "v1"
        }
      ],
      "case_set": {
        "identifier": "cases",
        "version": "v1"
      },
      "case_ids": [
        "case-one",
        "case-two"
      ],
      "evaluation_profile": {
        "identifier": "profile",
        "version": "v1"
      },
      "registry_digest": "863390a850efdedf8325d50326d9b63237f962a702df2c81844046b52d2afb65",
      "configuration_version": "zero-cost.jobs.v1",
      "configuration_digest": "dbb8023b293add83c490ed4cda87b02928cb7c2305d1ba14c83372f6bd293adb",
      "execution_digest": "5e9fd59a6e382e2efe90a2be616c588fdc592a71fdc8678289ace63bbc04f2bd",
      "provenance": "test",
      "case_set_digest": "40dbfd689fb286b9c1250babcf5a4b98f7646bdaa0a27c8d6b99a297ecd3b938",
      "evaluation_profile_digest": "090c8f81bf71faad2dd86468d39b36ac78fdd749c88163904487f6bb3c6777fa"
    },
    "approval_manifest_digest": null,
    "recording_dataset_digest": null,
    "quality_threshold": "0.92",
    "provenance": "test",
    "status": "complete",
    "decisions": [
      {
        "analysis_id": "analysis_5dca3dad3cee4697b67de955d385d92f",
        "node_id": "llm_4d6f1d6629a81593fae3739f",
        "provenance": "test",
        "status": "recommended",
        "reason": "lowest_recorded_cost",
        "baseline_model_id": "local/baseline",
        "selected_model_id": "local/candidate",
        "differs_from_baseline": true,
        "quality_threshold": "0.92",
        "candidates": [
          {
            "model": {
              "identifier": "local/baseline",
              "version": "v1"
            },
            "provenance": "test",
            "eligibility": "eligible",
            "reasons": [],
            "planned_cases": 2,
            "passed_cases": 2,
            "failed_cases": 0,
            "unresolved_cases": 0,
            "quality_pass_rate": "1.000000",
            "cost_total_usd": "2.00",
            "latency_ms": {
              "availability": "unavailable",
              "unit": "ms",
              "sample_count": 0,
              "minimum": null,
              "maximum": null,
              "mean": null,
              "total_tokens": null,
              "total_usd": null,
              "reason": "empty_population"
            },
            "measurement_digest": "ba1e0205b73ba46e0963b9e8e20bbc56a219741c3eb357ac03edb446c73b5905"
          },
          {
            "model": {
              "identifier": "local/candidate",
              "version": "v1"
            },
            "provenance": "test",
            "eligibility": "eligible",
            "reasons": [],
            "planned_cases": 2,
            "passed_cases": 2,
            "failed_cases": 0,
            "unresolved_cases": 0,
            "quality_pass_rate": "1.000000",
            "cost_total_usd": "1.00",
            "latency_ms": {
              "availability": "unavailable",
              "unit": "ms",
              "sample_count": 0,
              "minimum": null,
              "maximum": null,
              "mean": null,
              "total_tokens": null,
              "total_usd": null,
              "reason": "empty_population"
            },
            "measurement_digest": "ec2871b4837b5ae7d4872e38a85d0a7e5e9a5ffeeb6f263cc5f9351d1fb8082b"
          }
        ],
        "recorded_savings_usd": "1.00"
      }
    ],
    "nodes_considered": 1,
    "nodes_eligible": 1,
    "nodes_recommended": 1,
    "nodes_retained": 0,
    "nodes_inconclusive": 0,
    "nodes_unavailable": 0,
    "decisions_complete": true,
    "diagnostics": []
  },
  "policy": {
    "status": "available",
    "reason": null,
    "route_count": 1,
    "yaml_content": "analysis_digest: c59419b2a1f8659b866ca4cdfbd3738b8f31ae8171169e83cd31cf47ddcb4237\nanalysis_id: analysis_5dca3dad3cee4697b67de955d385d92f\napproval_manifest_digest: null\nbenchmark_digest: d51e740e62587822605587c9379dde6f76a55a673d5428e0905dda3a6a2181d7\ncase_set:\n  identifier: cases\n  version: v1\ncase_set_digest: 40dbfd689fb286b9c1250babcf5a4b98f7646bdaa0a27c8d6b99a297ecd3b938\nconfiguration_digest: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\nconfiguration_version: zero-cost.optimizer.v1\ndecisions_complete: true\nevaluation_profile:\n  identifier: profile\n  version: v1\nevaluation_profile_digest: 090c8f81bf71faad2dd86468d39b36ac78fdd749c88163904487f6bb3c6777fa\nexecution_digest: 5e9fd59a6e382e2efe90a2be616c588fdc592a71fdc8678289ace63bbc04f2bd\nobjective_version: all-checks-then-cost.v1\nomitted_nodes: []\noptimization_digest: e5cff3909e306d08a931f00ef0b750cb120d7806ce420b0484d0afffc156b5ea\nprovenance: test\nrecording_dataset_digest: null\nregistry_digest: 863390a850efdedf8325d50326d9b63237f962a702df2c81844046b52d2afb65\nroutes:\n- baseline_model:\n    identifier: local/baseline\n    version: v1\n  case_count: 2\n  decision_status: recommended\n  latency_ms:\n    availability: unavailable\n    maximum: null\n    mean: null\n    minimum: null\n    reason: empty_population\n    sample_count: 0\n    total_tokens: null\n    total_usd: null\n    unit: ms\n  measurement_digest: ec2871b4837b5ae7d4872e38a85d0a7e5e9a5ffeeb6f263cc5f9351d1fb8082b\n  model:\n    identifier: local/candidate\n    version: v1\n  node_id: llm_4d6f1d6629a81593fae3739f\n  observed_case_pass_rate: '1.000000'\n  provenance: test\n  quality_threshold: '0.92'\n  reason: lowest_recorded_cost\n  recorded_baseline_cost_usd: '2.00'\n  recorded_savings_usd: '1.00'\n  recorded_selected_cost_usd: '1.00'\nrun_id: run_9282aefccc1c48fba41ce9abd0ef762f\nschema_version: cascaderouter.policy.v1\n",
    "digest": "41a073d6020437d443f44b23c07736e22faaabcce90f661cc0795b18259544cf"
  },
  "optimization_id": "opt_2f4ecc0165192771e0d60b379e11a7b17cc40ce03337fc4a21b7854edeabb100"
});
