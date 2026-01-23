# Intelligent Insurance Sales Agent: Second Brain Architecture with Multi-NoSQL Strategy

## Executive Summary

This document presents a production-ready architecture for an AI-powered Insurance Sales Agent that combines the Second Brain AI Assistant approach with four specialized NoSQL databases. The system creates emergent intelligence through strategic data orchestration, enabling capabilities impossible with single-database architectures.

**Key Innovation**: While traditional insurance systems store data in monolithic SQL databases, this architecture leverages each NoSQL type's unique strengths to create a distributed "brain" that thinks, remembers, predicts, and learns.

---

## 1. Architecture Overview

### 1.1 The Four-Brain Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    AGENTIC ORCHESTRATION LAYER                  │
│  (LangGraph / CrewAI Agents coordinating multi-DB operations)   │
└───────┬─────────────┬─────────────┬─────────────┬───────────────┘
        │             │             │             │
        ▼             ▼             ▼             ▼
┌───────────────┐ ┌──────────┐ ┌──────────┐ ┌─────────────┐
│   MEMORY      │ │ REASONING│ │  RECALL  │ │   PATTERN   │
│   MongoDB     │ │  Neo4j   │ │ Qdrant   │ │  InfluxDB   │
│ (Documents)   │ │ (Graphs) │ │ (Vectors)│ │ (TimeSeries)│
└───────────────┘ └──────────┘ └──────────┘ └─────────────┘
```

### 1.2 Second Brain Principles Applied to Insurance

The Second Brain architecture's core concepts map perfectly to insurance sales:

| Second Brain Concept | Insurance Application |
|---------------------|----------------------|
| **Contextual Retrieval** | Pull customer context (past claims, family policies, life events) when proposing new policies |
| **Parent Retrieval** | Navigate policy hierarchies (umbrella → auto → home) and family relationships |
| **Vector Search** | Match customer needs to policy features semantically ("I'm worried about my kids' future" → education policies) |
| **Agentic Workflows** | Autonomous agents handle lead qualification, risk assessment, cross-sell identification, and renewal optimization |

### 1.3 Why Four Databases?

**The Power of Specialization:**

Each database solves problems the others cannot:

1. **MongoDB** stores rich, schema-flexible documents (policies with varying riders, customer profiles with diverse data)
2. **Neo4j** reveals hidden connections (referral networks, correlated risks, family policy dependencies)
3. **Qdrant** understands semantic meaning (customer intent, policy similarity, case-based reasoning)
4. **InfluxDB** captures temporal dynamics (premium trends, seasonal buying patterns, lifecycle stage transitions)

**Emergent Capabilities:**

- **Cross-database insights**: Find customers whose graph relationships + time-series behavior + vector similarity suggest high conversion probability
- **Intelligent caching**: Hot paths determined by graph centrality, stored in MongoDB, indexed in Qdrant
- **Predictive orchestration**: Time-series patterns trigger graph traversals that load vector-searched documents

---

## 2. Database-Specific Roles & Schemas

### 2.1 MongoDB: The Memory Store

**Role**: Authoritative source for detailed, structured insurance domain entities.

#### Core Collections

```javascript
// customers collection
{
  _id: ObjectId("..."),
  customer_id: "CUST-2024-123456",
  personal_info: {
    name: "John Smith",
    dob: ISODate("1985-03-15"),
    occupation: "Software Engineer",
    income_bracket: "100k-150k",
    risk_tolerance: "moderate"
  },
  contact: {
    email: "john.smith@email.com",
    phone: "+1-555-0123",
    preferred_channel: "email",
    preferred_time: "evening"
  },
  life_events: [
    {
      event_type: "marriage",
      date: ISODate("2010-06-20"),
      impact_score: 0.85  // ML-generated relevance to insurance needs
    },
    {
      event_type: "first_child",
      date: ISODate("2015-09-10"),
      impact_score: 0.92
    },
    {
      event_type: "home_purchase",
      date: ISODate("2018-04-15"),
      impact_score: 0.88
    }
  ],
  financial_profile: {
    assets: {
      primary_home_value: 450000,
      vehicles: [
        {type: "sedan", value: 25000, year: 2021},
        {type: "suv", value: 35000, year: 2023}
      ],
      investment_accounts: 180000
    },
    liabilities: {
      mortgage: 320000,
      auto_loans: 28000
    }
  },
  interaction_history: [
    {
      date: ISODate("2024-01-15T14:30:00Z"),
      channel: "phone",
      agent_id: "AGT-456",
      summary: "Inquired about life insurance increase due to second child",
      sentiment: "positive",
      embedding_ref: "qdrant://interactions/vec-789"  // Reference to vector store
    }
  ],
  policies: [
    {
      policy_id: "POL-AUTO-789",
      type: "auto",
      status: "active",
      premium_annual: 1200,
      coverage_limit: 300000,
      deductible: 1000,
      start_date: ISODate("2021-06-01"),
      renewal_date: ISODate("2024-06-01"),
      riders: ["roadside_assistance", "rental_coverage"]
    },
    {
      policy_id: "POL-LIFE-456",
      type: "term_life",
      status: "active",
      premium_annual: 840,
      coverage_amount: 500000,
      term_years: 20,
      beneficiaries: ["neo4j://persons/PERS-SPOUSE-001"]  // Graph reference
    }
  ],
  risk_profile: {
    health_score: 82,  // 0-100, higher is better
    driving_record_score: 95,
    credit_score_bracket: "excellent",
    claim_frequency: 0.15,  // claims per year across all policies
    lifestyle_risks: ["occasional_smoker"],
    calculated_at: ISODate("2024-01-01T00:00:00Z")
  },
  sales_intelligence: {
    lifetime_value: 45000,  // predicted
    churn_risk: 0.12,  // 0-1 probability
    cross_sell_propensity: {
      home_insurance: 0.78,
      umbrella_policy: 0.65,
      disability_insurance: 0.52
    },
    next_best_action: "propose_umbrella_policy",
    calculated_by_agent: "cross_sell_agent_v2",
    last_updated: ISODate("2024-01-20T08:00:00Z")
  },
  metadata: {
    created_at: ISODate("2018-03-10T10:00:00Z"),
    updated_at: ISODate("2024-01-20T14:30:00Z"),
    data_quality_score: 0.94,
    completeness_percentage: 87
  }
}

// policies collection (master policy definitions)
{
  _id: ObjectId("..."),
  policy_template_id: "TMPL-LIFE-TERM-STANDARD-V3",
  policy_type: "term_life",
  name: "SecureLife Term 20",
  description: "20-year level term life insurance with guaranteed premiums",
  full_document: {
    sections: [
      {
        title: "Coverage Details",
        content: "This policy provides death benefit coverage...",
        embeddings_ref: "qdrant://policies/vec-section-123"
      },
      {
        title: "Exclusions",
        content: "Coverage does not apply to death resulting from...",
        embeddings_ref: "qdrant://policies/vec-section-124"
      }
    ],
    full_text: "... complete policy document ...",
    document_metadata: {
      version: "3.2",
      effective_date: ISODate("2023-01-01"),
      state_approvals: ["CA", "NY", "TX", "FL"]
    }
  },
  features: [
    {
      feature_id: "convertibility",
      name: "Conversion Option",
      description: "Convert to permanent life insurance without medical exam before age 65",
      value_proposition: "Flexibility for changing needs",
      cost_impact: "included",
      embedding_ref: "qdrant://features/vec-456"
    },
    {
      feature_id: "accelerated_benefit",
      name: "Accelerated Death Benefit",
      description: "Access up to 50% of death benefit if diagnosed with terminal illness",
      value_proposition: "Financial support during critical times",
      cost_impact: "small_rider_fee"
    }
  ],
  underwriting_criteria: {
    age_range: [18, 65],
    health_requirements: {
      min_health_score: 60,
      excluded_conditions: ["stage_4_cancer", "severe_heart_disease"],
      medical_exam_required: true
    },
    financial_requirements: {
      min_income: 30000,
      max_coverage_to_income_ratio: 20
    }
  },
  pricing_matrix: {
    base_rates: [
      {age_band: "18-25", rate_per_1000: 0.85},
      {age_band: "26-35", rate_per_1000: 1.05},
      {age_band: "36-45", rate_per_1000: 1.65},
      {age_band: "46-55", rate_per_1000: 2.95},
      {age_band: "56-65", rate_per_1000: 5.25}
    ],
    risk_multipliers: {
      smoker: 2.5,
      hazardous_occupation: 1.3,
      poor_health: 1.8
    }
  },
  sales_positioning: {
    target_segments: ["young_families", "high_earners", "mortgage_holders"],
    key_competitors: ["StateFarm TermLife", "Prudential Term"],
    competitive_advantages: [
      "30-day free look period vs 10-day industry standard",
      "Included accelerated death benefit"
    ],
    common_objections: [
      {
        objection: "Too expensive",
        rebuttal_strategy: "Show monthly cost vs daily coffee expense",
        rebuttal_ref: "qdrant://objections/vec-789"
      }
    ]
  }
}

// claims collection
{
  _id: ObjectId("..."),
  claim_id: "CLM-2023-789456",
  customer_id: "CUST-2024-123456",
  policy_id: "POL-AUTO-789",
  claim_type: "auto_accident",
  incident_date: ISODate("2023-11-15T16:45:00Z"),
  reported_date: ISODate("2023-11-15T18:20:00Z"),
  status: "settled",
  claim_amount: 8500,
  paid_amount: 7500,
  deductible_applied: 1000,
  incident_details: {
    description: "Rear-ended at traffic light, moderate damage to rear bumper and trunk",
    location: {
      address: "123 Main St, Anytown, CA",
      coordinates: [-122.4194, 37.7749]
    },
    weather_conditions: "clear",
    fault_determination: "not_at_fault",
    police_report_filed: true,
    witnesses: 2
  },
  processing_timeline: [
    {
      stage: "reported",
      date: ISODate("2023-11-15T18:20:00Z"),
      handled_by: "automated_intake_bot"
    },
    {
      stage: "adjuster_assigned",
      date: ISODate("2023-11-16T09:00:00Z"),
      handled_by: "ADJ-123"
    },
    {
      stage: "inspection_completed",
      date: ISODate("2023-11-18T14:30:00Z")
    },
    {
      stage: "approved",
      date: ISODate("2023-11-20T10:15:00Z")
    },
    {
      stage: "settled",
      date: ISODate("2023-11-25T16:00:00Z")
    }
  ],
  impact_on_customer: {
    premium_increase_next_renewal: 0,  // not at fault
    risk_score_impact: -2,  // slight improvement for good reporting behavior
    customer_satisfaction_rating: 5,  // 1-5 scale
    likelihood_to_renew: 0.92  // ML prediction
  },
  similar_claims_ref: "qdrant://claims/cluster-456",  // Vector similarity cluster
  fraud_score: 0.05,  // 0-1, ML-generated
  related_claims_graph: "neo4j://claims/CLM-2023-789456"  // Graph connections
}

// interactions collection
{
  _id: ObjectId("..."),
  interaction_id: "INT-2024-001234",
  customer_id: "CUST-2024-123456",
  timestamp: ISODate("2024-01-20T14:30:00Z"),
  channel: "phone",
  direction: "inbound",
  agent_id: "AGT-456",
  duration_seconds: 1245,
  transcript: {
    full_text: "Agent: Thank you for calling SecureLife Insurance...",
    turns: [
      {
        speaker: "agent",
        text: "Thank you for calling SecureLife Insurance, this is Sarah. How can I help you today?",
        timestamp_offset: 0
      },
      {
        speaker: "customer",
        text: "Hi Sarah, I'm calling because my wife and I just found out we're expecting our second child...",
        timestamp_offset: 8,
        detected_intent: "life_event_notification",
        detected_needs: ["increased_life_coverage", "education_planning"],
        sentiment: "positive_excited"
      }
    ],
    embedding_ref: "qdrant://transcripts/vec-001234"
  },
  outcome: {
    resolution: "quote_generated",
    products_discussed: ["term_life_increase", "education_savings_policy"],
    quote_ids: ["QUO-2024-5678"],
    follow_up_scheduled: ISODate("2024-01-27T15:00:00Z"),
    next_action: "send_quote_comparison_email"
  },
  analytics: {
    customer_sentiment_journey: [
      {minute: 0, sentiment: 0.7},
      {minute: 5, sentiment: 0.8},
      {minute: 10, sentiment: 0.6},  // discussing premium increase
      {minute: 15, sentiment: 0.85}  // after explaining value
    ],
    topics_detected: ["life_insurance", "child_planning", "budget_concerns"],
    objections_handled: ["price_concern"],
    agent_performance_score: 0.88
  }
}
```

#### Indexing Strategy

```javascript
// Performance-critical indexes
db.customers.createIndex({"customer_id": 1}, {unique: true})
db.customers.createIndex({"contact.email": 1})
db.customers.createIndex({"sales_intelligence.churn_risk": -1})
db.customers.createIndex({"sales_intelligence.cross_sell_propensity.home_insurance": -1})
db.customers.createIndex({"life_events.date": -1})
db.customers.createIndex({"policies.renewal_date": 1})

// Compound index for agent workflow queries
db.customers.createIndex({
  "sales_intelligence.churn_risk": -1,
  "policies.renewal_date": 1
})

// Text search for customer service
db.interactions.createIndex({"transcript.full_text": "text"})

// Time-based queries
db.claims.createIndex({"incident_date": -1})
db.claims.createIndex({"customer_id": 1, "status": 1})
```

#### MongoDB's Unique Value

1. **Flexible schema evolution**: Insurance products change frequently; MongoDB handles policy variations without schema migrations
2. **Rich query capabilities**: Complex aggregations for sales intelligence (e.g., "customers with 2+ policies, high cross-sell propensity, renewal in 60 days")
3. **Document-level atomicity**: Critical for financial transactions and policy updates
4. **Embedded arrays**: Natural fit for policy riders, beneficiaries, interaction history

---

### 2.2 Neo4j: The Reasoning Engine

**Role**: Uncover hidden relationships, propagate risk signals, map influence networks, and enable graph-based reasoning.

#### Node Types & Relationships

```cypher
// Core node types
(:Person {
  id: "PERS-123",
  name: "John Smith",
  dob: date("1985-03-15"),
  mongodb_ref: "CUST-2024-123456"
})

(:Policy {
  id: "POL-AUTO-789",
  type: "auto",
  status: "active",
  annual_premium: 1200,
  coverage_limit: 300000,
  mongodb_ref: "POL-AUTO-789"
})

(:Address {
  id: "ADDR-456",
  street: "123 Main St",
  city: "Anytown",
  state: "CA",
  zip: "94102",
  risk_zone: "moderate",
  flood_risk_score: 0.3,
  crime_risk_score: 0.2
})

(:Agent {
  id: "AGT-456",
  name: "Sarah Johnson",
  specialization: ["life_insurance", "family_planning"],
  performance_score: 0.92,
  book_size: 450
})

(:Vehicle {
  id: "VEH-789",
  make: "Toyota",
  model: "Camry",
  year: 2021,
  vin: "1HGBH41JXMN109186"
})

(:Claim {
  id: "CLM-2023-789456",
  type: "auto_accident",
  amount: 8500,
  date: datetime("2023-11-15T16:45:00Z"),
  mongodb_ref: "CLM-2023-789456"
})

(:RiskFactor {
  id: "RISK-FLOOD-CA-94102",
  type: "flood",
  severity: "moderate",
  geographic_scope: "zip_code"
})

(:LifeEvent {
  id: "EVT-BIRTH-2024-001",
  type: "child_birth",
  date: date("2024-03-15"),
  insurance_impact_score: 0.92
})

(:Product {
  id: "PROD-LIFE-TERM-20",
  name: "SecureLife Term 20",
  category: "life_insurance",
  mongodb_ref: "TMPL-LIFE-TERM-STANDARD-V3"
})

// Relationship types with rich properties

// Family & Social Network
(:Person)-[:MARRIED_TO {since: date("2010-06-20")}]->(:Person)
(:Person)-[:PARENT_OF {role: "primary_guardian"}]->(:Person)
(:Person)-[:REFERRED_BY {
  date: date("2023-05-10"),
  incentive_paid: 250,
  conversion_date: date("2023-06-15")
}]->(:Person)
(:Person)-[:WORKS_WITH]->(:Person)
(:Person)-[:LIVES_WITH {relationship: "domestic_partner"}]->(:Person)

// Policy Relationships
(:Person)-[:HOLDS_POLICY {
  role: "primary_insured",
  since: date("2021-06-01"),
  premium_payment_method: "auto_debit"
}]->(:Policy)
(:Person)-[:BENEFICIARY_OF {
  percentage: 100,
  designation: "primary",
  relationship: "spouse"
}]->(:Policy)
(:Policy)-[:COVERS {item_type: "vehicle"}]->(:Vehicle)
(:Policy)-[:COVERS {item_type: "property"}]->(:Address)
(:Policy)-[:UMBRELLA_OVER]->(:Policy)  // Umbrella policy covering other policies
(:Policy)-[:BUNDLED_WITH {discount_percentage: 15}]->(:Policy)

// Risk & Claims
(:Person)-[:FILED_CLAIM {role: "claimant"}]->(:Claim)
(:Policy)-[:CLAIM_AGAINST]->(:Claim)
(:Claim)-[:OCCURRED_AT]->(:Address)
(:Claim)-[:INVOLVED_VEHICLE]->(:Vehicle)
(:Claim)-[:RELATED_TO_CLAIM {
  correlation_type: "same_incident",
  confidence: 0.95
}]->(:Claim)
(:Address)-[:HAS_RISK_FACTOR {exposure_level: "high"}]->(:RiskFactor)
(:Person)-[:EXPOSED_TO {through: "residence"}]->(:RiskFactor)

// Life Events & Triggers
(:Person)-[:EXPERIENCED {
  verified: true,
  source: "customer_reported"
}]->(:LifeEvent)
(:LifeEvent)-[:TRIGGERS_NEED_FOR]->(:Product)

// Agent & Sales
(:Agent)-[:MANAGES_ACCOUNT {since: date("2021-06-01")}]->(:Person)
(:Agent)-[:SOLD {
  commission: 840,
  sale_date: date("2021-06-01")
}]->(:Policy)
(:Agent)-[:SPECIALIZES_IN]->(:Product)
(:Agent)-[:MENTORED_BY]->(:Agent)

// Product & Underwriting
(:Product)-[:SUITABLE_FOR {
  fit_score: 0.85,
  reason: "age_income_match"
}]->(:Person)
(:Product)-[:COMPETES_WITH {
  win_rate: 0.65
}]->(:Product)
(:Product)-[:COMMONLY_BUNDLED_WITH {
  bundle_rate: 0.45
}]->(:Product)
```

#### Key Graph Patterns & Queries

**Pattern 1: Referral Network Analysis**

```cypher
// Find high-value customers in strong referral networks
// (These are ideal for referral incentive campaigns)
MATCH (customer:Person)-[:HOLDS_POLICY]->(p:Policy)
WHERE p.status = 'active'
WITH customer, sum(p.annual_premium) as total_premium
WHERE total_premium > 3000

MATCH network_path = (customer)-[:REFERRED_BY*1..3]-(connected:Person)
WITH customer, total_premium,
     count(DISTINCT connected) as network_size,
     collect(DISTINCT connected) as network_members

// Check how many in network are also customers
MATCH (network_member:Person)-[:HOLDS_POLICY]->(:Policy)
WHERE network_member IN network_members
WITH customer, total_premium, network_size,
     count(DISTINCT network_member) as customer_network_size

// Calculate network value and influence
WITH customer, total_premium, network_size,
     customer_network_size,
     toFloat(customer_network_size) / network_size as network_conversion_rate

WHERE network_conversion_rate > 0.5
  AND network_size >= 5

RETURN customer.name,
       customer.mongodb_ref,
       total_premium,
       network_size,
       customer_network_size,
       round(network_conversion_rate * 100, 2) as conversion_percentage,
       total_premium * network_size * network_conversion_rate as network_lifetime_value
ORDER BY network_lifetime_value DESC
LIMIT 50
```

**Pattern 2: Correlated Risk Discovery**

```cypher
// Identify customers sharing risk factors with recent claim activity
// (Proactive risk management and potential premium adjustments)
MATCH (recent_claim:Claim)<-[:FILED_CLAIM]-(claimant:Person)
WHERE recent_claim.date > datetime() - duration({months: 6})
  AND recent_claim.amount > 5000

// Find risk factors associated with this claim
MATCH (recent_claim)-[:OCCURRED_AT]->(location:Address)-[:HAS_RISK_FACTOR]->(risk:RiskFactor)

// Find other customers exposed to same risk
MATCH (risk)<-[:EXPOSED_TO]-(at_risk_customer:Person)-[:HOLDS_POLICY]->(policy:Policy)
WHERE at_risk_customer <> claimant
  AND policy.status = 'active'
  AND NOT (at_risk_customer)-[:FILED_CLAIM]->(:Claim)-[:OCCURRED_AT]->(location)

// Calculate their exposure score
WITH at_risk_customer,
     collect(DISTINCT risk) as shared_risks,
     count(DISTINCT policy) as policy_count,
     sum(policy.coverage_limit) as total_exposure

RETURN at_risk_customer.name,
       at_risk_customer.mongodb_ref,
       [r IN shared_risks | r.type] as risk_types,
       size(shared_risks) as risk_count,
       policy_count,
       total_exposure,
       round(size(shared_risks) * total_exposure / 100000.0, 2) as risk_score
ORDER BY risk_score DESC
LIMIT 100
```

**Pattern 3: Cross-Sell Opportunity Graph Walk**

```cypher
// Find customers with life stage + risk exposure + social proof for umbrella policies
MATCH (customer:Person)-[:EXPERIENCED]->(life_event:LifeEvent)
WHERE life_event.type IN ['home_purchase', 'marriage', 'high_income_promotion']
  AND life_event.date > date() - duration({years: 2})

// Check their current policy portfolio
MATCH (customer)-[:HOLDS_POLICY]->(current_policy:Policy)
WHERE current_policy.status = 'active'

WITH customer,
     collect(DISTINCT current_policy.type) as policy_types,
     sum(current_policy.coverage_limit) as total_coverage

// They must have both home and auto (umbrella requirement)
WHERE 'home' IN policy_types
  AND 'auto' IN policy_types
  AND total_coverage >= 500000
  AND NOT 'umbrella' IN policy_types

// Find referral network social proof
MATCH (customer)-[:REFERRED_BY|MARRIED_TO|WORKS_WITH*1..2]-(peer:Person)
      -[:HOLDS_POLICY]->(peer_policy:Policy {type: 'umbrella'})

WITH customer, policy_types, total_coverage,
     count(DISTINCT peer) as peers_with_umbrella

WHERE peers_with_umbrella >= 2

// Get their agent relationship
MATCH (agent:Agent)-[:MANAGES_ACCOUNT]->(customer)

RETURN customer.name,
       customer.mongodb_ref,
       policy_types,
       total_coverage,
       peers_with_umbrella,
       agent.name as assigned_agent,
       'high_propensity_umbrella' as opportunity_type
ORDER BY peers_with_umbrella DESC, total_coverage DESC
```

**Pattern 4: Policy Dependency Chains**

```cypher
// Map policy dependencies for churn prevention
// (If customer cancels home policy, we might lose bundled auto policy too)
MATCH (customer:Person)-[:HOLDS_POLICY]->(anchor_policy:Policy)
WHERE anchor_policy.status = 'active'

// Find all policies connected through bundling or umbrella relationships
MATCH policy_chain = (anchor_policy)-[:BUNDLED_WITH|UMBRELLA_OVER*0..3]-(dependent:Policy)
WHERE dependent.status = 'active'

WITH customer, anchor_policy,
     collect(DISTINCT dependent) as dependent_policies,
     relationships(policy_chain) as rels

// Calculate financial impact of losing anchor policy
WITH customer, anchor_policy, dependent_policies,
     anchor_policy.annual_premium as anchor_premium,
     reduce(total = 0, p IN dependent_policies |
       total + p.annual_premium) as dependent_premium

// Factor in bundle discounts that would be lost
WITH customer, anchor_policy, dependent_policies,
     anchor_premium + dependent_premium as total_at_risk,
     size(dependent_policies) as dependency_count

WHERE dependency_count > 0

RETURN customer.name,
       customer.mongodb_ref,
       anchor_policy.type as anchor_type,
       anchor_policy.id as anchor_policy_id,
       [p IN dependent_policies | p.type] as dependent_types,
       dependency_count,
       anchor_premium,
       total_at_risk,
       round(total_at_risk / anchor_premium, 2) as risk_multiplier
ORDER BY total_at_risk DESC
```

**Pattern 5: Agent Expertise Matching**

```cypher
// Match customers with complex needs to agents with relevant experience
MATCH (customer:Person)-[:HOLDS_POLICY]->(policy:Policy)
WHERE policy.renewal_date > date()
  AND policy.renewal_date < date() + duration({days: 90})

// Identify customer complexity factors
MATCH (customer)-[:EXPERIENCED]->(life_event:LifeEvent)
WHERE life_event.date > date() - duration({months: 6})

OPTIONAL MATCH (customer)-[:FILED_CLAIM]->(claim:Claim)
WHERE claim.date > date() - duration({years: 2})

WITH customer, policy,
     collect(DISTINCT life_event.type) as recent_life_events,
     count(DISTINCT claim) as recent_claims,
     CASE
       WHEN count(DISTINCT claim) > 2 THEN 'high_complexity'
       WHEN size(collect(DISTINCT life_event.type)) > 0 THEN 'medium_complexity'
       ELSE 'low_complexity'
     END as complexity_tier

// Find current agent
MATCH (current_agent:Agent)-[:MANAGES_ACCOUNT]->(customer)

// Find alternative agents with better fit
MATCH (product:Product)<-[:TRIGGERS_NEED_FOR]-(life_event_type:LifeEvent)
WHERE life_event_type.type IN recent_life_events

MATCH (specialist_agent:Agent)-[:SPECIALIZES_IN]->(product)
WHERE specialist_agent <> current_agent
  AND specialist_agent.performance_score > current_agent.performance_score

RETURN customer.name,
       customer.mongodb_ref,
       policy.type as renewal_policy_type,
       policy.renewal_date,
       complexity_tier,
       recent_life_events,
       current_agent.name as current_agent,
       current_agent.performance_score as current_score,
       collect(DISTINCT specialist_agent.name)[0..3] as recommended_specialists,
       avg(specialist_agent.performance_score) as specialist_avg_score
ORDER BY complexity_tier DESC, policy.renewal_date ASC
```

#### Neo4j's Unique Value

1. **Relationship-first thinking**: Insurance is fundamentally about relationships (policies to people, risks to locations, claims to incidents)
2. **Pattern matching**: Fraud detection, referral network analysis, and risk correlation are graph problems
3. **Path finding**: Discover indirect connections (customer → coworker → claimant) for fraud or opportunity discovery
4. **Real-time traversals**: Sub-second queries for "find all policies affected if this customer churns"
5. **Influence propagation**: Model how life events ripple through family networks to create sales opportunities

---


### 2.3 Qdrant: The Semantic Recall Engine

**Role**: Enable semantic understanding, similarity matching, and contextual retrieval through vector embeddings.

#### Collections & Vector Spaces

```python
# Collection structure in Qdrant

# 1. Policy Documents Collection
collection_name = "policy_documents"
vector_config = {
    "content_dense": {  # Dense embeddings from large models
        "size": 1536,  # OpenAI ada-002 or similar
        "distance": "Cosine"
    },
    "content_sparse": {  # Sparse embeddings for keyword matching
        "size": 30000,
        "distance": "Cosine",
        "type": "sparse"
    }
}

# Example policy document point
{
    "id": "pol-doc-section-123",
    "vector": {
        "content_dense": [0.023, -0.154, ...],  # 1536 dimensions
        "content_sparse": {"indices": [45, 892, 1234], "values": [0.8, 0.6, 0.9]}
    },
    "payload": {
        "policy_template_id": "TMPL-LIFE-TERM-STANDARD-V3",
        "section_type": "coverage_details",
        "title": "Coverage Details",
        "content": "This policy provides death benefit coverage of $500,000...",
        "keywords": ["death_benefit", "coverage", "term_life"],
        "mongodb_ref": "TMPL-LIFE-TERM-STANDARD-V3",
        "policy_type": "term_life"
    }
}
```

(The full Qdrant section is about 800 lines - continuing with the critical parts)

