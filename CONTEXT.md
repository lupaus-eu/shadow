# Shadow

The domain of modelling an organisation as a digital twin: its structure as a
graph over time, its metrics as timeseries, its history and plans as events
and scenarios, and forecasts of its metrics.

This glossary is the canonical vocabulary. Each term's full meaning,
invariants, and lifecycle are in its concept document under
[`docs/architecture/concepts/`](docs/architecture/concepts/CONCEPTS.md); data,
API, and rule ownership is in
[`docs/architecture/domains/`](docs/architecture/domains/DOMAIN.md).

## Language

**Organisation**:
The organisation being modelled: the stable boundary that contains its Scenarios, Organisation States, and organisation-specific Metamodel. Written with *s*.
_Avoid_: Tenant, Customer, Company (an Organisation is modelled, it does not subscribe)

**Scenario**:
A versioned planning or analysis context within one Organisation. A Scenario owns its Organisation States, Events, Timeseries, and graph history; a copy of a Scenario is an editable branch ("Fork of …").
_Avoid_: Organisation State, version

**Reality**:
The default, protected Scenario that every Organisation has, describing the organisation as it is.

**Organisation State**:
A named, Scenario-specific snapshot of an Organisation at a target date. Its graph is the projection of the Scenario's graph history onto that date.
_Avoid_: Scenario, snapshot of the whole Organisation

**Event**:
A dated item on a Scenario's event timeline, with a target date.

**Timeserie** (plural **Timeseries**):
A Scenario-owned metric definition (short name, value unit, and time unit) together with its dated values. Values must match the value unit and start on a valid date for the time unit.

**Derived Metric**:
A numeric Timeserie whose values are calculated from one stored formula over other Timeseries of the same Scenario. Its values are read-only.

**Metamodel**:
The type model that describes and validates an Organisation's twin graph: node types, edge types, type attributes, and allowed connections. There is one default Metamodel; an Organisation may have its own.

**Graph node** and **Graph edge**:
The elements of a Scenario's organisation twin graph, typed by the Metamodel and valid over a period of time.

**Prediction Version**:
A named, immutable, comparable forecast for an Organisation's Scenario metrics, kept distinct from manually entered Timeserie values.
_Avoid_: Timeserie values, Scenario

**Prediction Request**:
A durable request to calculate a Prediction Version, processed in the background by the prediction worker from an immutable snapshot.

**AI Change Set**:
An Organisation-scoped, ordered list of typed operations staged by a person's AI client through MCP. It is validated by a dry run, frozen on submit, and applied atomically only when a human approves it, in Shadow or in the MCP client.
_Avoid_: AI Extraction (a separate, unplanned candidate concept)

**Customer**:
A customer or customer organisation of the company using Shadow, with its Contacts and Customer Addresses.
_Avoid_: Organisation, Invoice, User

**Account class**:
Whether a User account is a `customer` account (it signs in to the application) or a `platform` account (an operator, used only in the separate platform console). Existing and new Users are customer accounts; application routes, the Users API, MCP grants and the application's sign-in treat only customer accounts as Users (ADR-016).
_Avoid_: role (a role says what a customer account may do)

**User**:
A person with access to Shadow. Today every User has one application-wide role, `admin` or `consultant`, and both may use every Organisation; `admin` also administers Users.
_Avoid_: Contact

## Under specification

These terms come from the SaaS platform plan (`.scratch/saas-platform/PLAN.md`)
and are **not yet canonical**. Settle them in the tenancy PRD and move them to
*Language* when accepted.

- The subscribing company (Yearclock's *Organization*): proposed code name
  `tenant`, shown as "Company", to avoid a clash with **Organisation**.
- **Membership** of a person in a company, with the roles **Owner**, **Admin**,
  and **Member**.
- **Platform account** of an operator, with the roles **Platform Admin** and
  **Support Agent**, used only in the separate platform console. Its *account
  class* is canonical (see **Account class**); the console and its roles arrive
  with step 7 of the plan.
- **Seat**, **Subscription**, **Legal document**, and **Support Access** as in
  Yearclock.
