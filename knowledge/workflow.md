# Workflow for the Analysis of Territorial Critical Situations in Tourism Management

## Purpose

This workflow supports the analysis and management of critical situations affecting a territory in the context of tourism. Its goal is to identify relevant factors, model their relationships, and evaluate how potential interventions affect the overall system.

The workflow combines expert-driven territorial modelling with a Digital Twin that allows non-expert users to explore and compare possible interventions.

---

## 1. Identify Relevant Elements and Stakeholders

The first step is to understand the critical situation and identify the elements that are relevant to the selected location.

Depending on the problem, relevant elements may include:

* Available parking capacity
* Tourist and resident flows
* Seasonality and peak periods
* Number and capacity of hotels and accommodation facilities
* Transport infrastructure and mobility services
* Tourist attractions and facilities
* Environmental or spatial constraints
* Local services and public infrastructure

For each element, identify:

* Available or required data
* Data sources
* Relevant stakeholders responsible for, affected by, or able to influence the element

Typical stakeholders may include local authorities, tourism operators, transport providers, accommodation providers, residents, and infrastructure managers.

The output of this step is a structured description of the relevant elements, stakeholders, and available data.

---

## 2. Model the Current Situation

The identified elements and their relationships must be represented as a model of the territory.

This activity should ideally be supervised or performed by a data analyst or other domain expert. One possible approach is to implement the model as a **Civic Digital Twin**, representing the relevant components of the locality, their relationships, constraints, and measurable behaviours.

The model should describe the **As-is Scenario**, representing the current situation as accurately as possible using the available data.

Examples of relationships include:

* More visitors may increase parking demand and mobility congestion.
* Increasing accommodation capacity may increase tourist flows.
* Mobility restrictions may reduce congestion while affecting accessibility.
* An intervention that improves one KPI may negatively affect another part of the system.

The output is a Digital Twin that can be used to simulate changes and evaluate their consequences.

---

## 3. Define and Evaluate Changes

Potential interventions are applied to the As-is Scenario to create alternative scenarios.

Each scenario represents a specific configuration of changes. The Digital Twin is used to evaluate the consequences of those changes on relevant elements, constraints, and performance indicators.

The analysis should answer questions such as:

* Does the intervention improve the overall situation?
* Which KPIs improve or worsen?
* Does solving one problem create negative consequences elsewhere?
* Are there trade-offs between different stakeholders or objectives?
* Which alternative provides the best overall outcome?

The result is a comparison of alternative scenarios based on computed KPIs, metrics, and model outputs.

---

# Software Workflow

Our software uses a Digital Twin of a locality, created and maintained with the support of data analysts, to allow non-expert users to explore critical situations and evaluate possible interventions.

The user-facing workflow is based on three main concepts.

## Problems

A **Problem** is a critical situation or phenomenon to be analysed or managed within the platform.

A Problem is the top-level concept and contains one or more Proposals.

### Examples

* Overcrowding in a specific location
* Lack of parking in a city during the summer season
* Mobility congestion during peak season

---

## Proposals

A **Proposal** is a possible strategy or intervention designed to address a specific Problem.

A Proposal groups one or more Scenarios that explore different parameter configurations for that strategy. Each Proposal belongs to exactly one Problem.

### Examples

* Introduce visitor caps
* Promote off-peak mobility incentives
* Increase parking capacity
* Introduce access restrictions during peak periods

---

## Scenarios

A **Scenario** is a simulation run that explores the consequences of a specific set of changes applied to the As-is Scenario.

Scenarios are used to evaluate and compare alternative configurations of one or more strategies. A Scenario may be associated with different Proposals when it is relevant to evaluating multiple approaches.

Each Scenario is evaluated using the [Digital Twin](digital-twin.md).

The evaluation produces output data associated with the Scenario, including:

* KPIs
* Metrics
* Model outputs
* Constraint violations or trade-offs
* Other indicators required to compare scenarios

### Examples

* Visitor cap at 500 visitors per day
* Visitor cap at 1,000 visitors per day
* Double the number of parking spaces
* Increase public transport capacity by 20%

---

# Overall Procedure

The complete workflow can be summarised as:

1. **Identify the critical situation** and the relevant territorial elements.
2. **Identify stakeholders and data sources** associated with those elements.
3. **Build or update the Digital Twin**, modelling elements, relationships, constraints, and the As-is Scenario.
4. **Create a Problem** representing the critical situation to be analysed.
5. **Create one or more Proposals** representing possible strategies.
6. **Create Scenarios** by defining specific changes or parameter values.
7. **Run the Scenario evaluation** using the Digital Twin.
8. **Compare results** using KPIs, metrics, constraints, and other model outputs.
9. **Assess overall impact**, considering both improvements and possible negative consequences or trade-offs.

The key principle is that interventions should not be evaluated only according to whether they solve a single issue. The Digital Twin should support a systemic evaluation of the territory, helping users identify whether a proposed change produces an overall improvement or simply shifts the problem to another element of the system.
