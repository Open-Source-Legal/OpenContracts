# Badge System Implementation

## Status: Complete ✅

The badge system allows admins to create badges (global or corpus-specific) that can be manually awarded or automatically awarded based on configurable criteria.

## Overview

**Key Design Decisions:**

- **Two badge types**: GLOBAL (site-wide) and CORPUS (specific to a corpus)
- **Two award modes**: Manual (admin awards) and Auto-award (triggers on user actions)
- **Registry-based criteria**: Extensible system with declarative criteria type definitions
- **Multi-layer validation**: Frontend, GraphQL, Django model, and database constraints
- **Signal-driven**: Automatic badge checks triggered by user actions (messages, annotations)
- **Dynamic UI**: Frontend adapts to selected criteria type via GraphQL introspection

## Default Badges

The system automatically installs 9 default global badges via migration `0005_install_default_badges.py`:

**Engagement Badges:**
- **First Steps** (🟢 green) - First message posted
- **Conversationalist** (🔵 blue) - 10 messages posted
- **Active Contributor** (🟣 purple) - 50 messages posted
- **Discussion Leader** (🎀 pink) - 100 messages posted

**Reputation Badges:**
- **Helpful** (🟢 green) - Earned 10 reputation points
- **Valued Contributor** (🟡 yellow) - Earned 50 reputation points
- **Expert** (🟠 orange) - Earned 100 reputation points
- **Master** (🔴 red) - Earned 500 reputation points

**Quality Badge:**
- **Popular Post** (🟡 amber) - Received 10 upvotes on a single message

All default badges are auto-awarded and created by a system user on first migration.

## Backend Implementation

### 1. Models (`opencontractserver/badges/models.py`)

**Badge Model:**
- Fields: name, description, icon (lucide-react icon name), color (hex), badge_type, corpus FK (nullable)
- Auto-award fields: `is_auto_awarded`, `criteria_config` (JSONField)
- Validation in `clean()`: criteria_config validated against registry, scope compatibility checked

**UserBadge Model:**
- Junction table: user FK, badge FK, awarded_by FK (nullable for auto-awards), corpus FK (nullable)
- Unique constraints: `unique_user_badge_global`, `unique_user_badge_corpus`

### 2. Criteria Registry (`opencontractserver/badges/criteria_registry.py`)

**Registry Pattern:**
```python
@dataclass
class CriteriaField:
    name: str
    label: str
    field_type: str  # "number", "text", "boolean"
    required: bool
    description: str
    min_value: Optional[int] = None
    max_value: Optional[int] = None
    allowed_values: Optional[List[str]] = None

@dataclass
class CriteriaTypeDefinition:
    type_id: str
    name: str
    description: str
    scope: str  # "global", "corpus", "both"
    fields: List[CriteriaField]
    implemented: bool
```

**Pre-configured Criteria Types:**
- `first_post`: User's first message (no config needed)
- `message_count`: User reaches N messages (config: value)
- `corpus_contribution`: User adds N documents/annotations to corpus (config: value)
- `reputation_threshold`: User reaches reputation score (config: value) - ✅ IMPLEMENTED
- `message_upvotes`: User gets message with N upvotes (config: value) - ✅ IMPLEMENTED

**Adding New Criteria:**
1. Register in `criteria_registry.py`:
   ```python
   BadgeCriteriaRegistry.register(
       CriteriaTypeDefinition(
           type_id="my_criteria",
           name="My Criteria",
           description="Description",
           scope="both",
           fields=[CriteriaField(name="threshold", ...)],
           implemented=True
       )
   )
   ```
2. Implement evaluation logic in `badge_tasks.py`:
   ```python
   elif criteria_type == "my_criteria":
       threshold = badge.criteria_config.get("threshold")
       return check_my_condition(user, threshold, corpus)
   ```

### 3. GraphQL Schema

**Types (`config/graphql/graphene_types.py`):**
- `BadgeType`: Badge details with permission fields
- `UserBadgeType`: Badge award record
- `CriteriaFieldType`: Field definition from registry
- `CriteriaTypeDefinitionType`: Complete criteria type metadata

**Queries (`config/graphql/queries.py`):**
- `badges(corpusId, limit, offset)`: List badges
- `userBadges(userId, corpusId)`: List user's earned badges
- `badgeCriteriaTypes(scope)`: Get available criteria types from registry

**Mutations (`config/graphql/badge_mutations.py`):**
- `createBadge`: Validates criteria_config against registry before creation
- `updateBadge`: Validates final state after updates
- `deleteBadge`: Remove badge and all awards
- `awardBadge`: Manually award badge to user
- `revokeBadge`: Remove badge from user

### 4. Signal Handlers (`opencontractserver/badges/signals.py`)

**Automatic Badge Checks:**
- `@receiver(post_save, sender="conversations.ChatMessage")`: Triggers badge checks on message creation
- `@receiver(post_save, sender="annotations.Annotation")`: Triggers badge checks on annotation creation
- Both check global badges and corpus-specific badges (if applicable)
- Use `instance._skip_signals = True` in tests to prevent automatic awards

### 5. Badge Evaluation (`opencontractserver/tasks/badge_tasks.py`)

**Key Tasks:**
- `check_auto_badges(user_id, corpus_id)`: Check all auto-award badges for user
- `check_badges_for_all_users(corpus_id)`: Bulk check for all active users
- `revoke_badges_by_criteria(badge_id)`: Remove badges from users who no longer meet criteria

**Evaluation Flow:**
1. Validate criteria_config against registry
2. Extract criteria type and parameters
3. Query database for user's stats
4. Compare against threshold
5. Award badge if met (and not already awarded)

## Frontend Implementation

### 1. GraphQL Query (`frontend/src/graphql/queries.ts`)

```typescript
export const GET_BADGE_CRITERIA_TYPES = gql`
  query GetBadgeCriteriaTypes($scope: String) {
    badgeCriteriaTypes(scope: $scope) {
      typeId
      name
      description
      scope
      fields { name, label, fieldType, required, description, minValue, maxValue, allowedValues }
      implemented
    }
  }
`;
```

### 2. Dynamic Criteria Config Component (`frontend/src/components/badges/BadgeCriteriaConfig.tsx`)

**Purpose:** Dynamically render form fields based on selected criteria type

**Flow:**
1. Fetch criteria types from backend via `badgeCriteriaTypes` query
2. Filter to scope (global or corpus) based on badge type
3. Render dropdown with available criteria types
4. When type selected, render dynamic fields based on field definitions
5. Validate inputs in real-time
6. Pass validated config to parent via `onChange({ config, isValid })`

**Field Rendering:**
- `number`: `<Input type="number" min={minValue} max={maxValue} />`
- `text` (no allowedValues): `<Input type="text" />`
- `text` (with allowedValues): `<Dropdown options={allowedValues} />`
- `boolean`: `<Dropdown options={[true, false]} />`

### 3. Badge Management UI (`frontend/src/components/badges/BadgeManagement.tsx`)

**Integration:**
- Auto-award checkbox shows/hides BadgeCriteriaConfig component
- Create button disabled if auto-award enabled but criteria invalid
- Passes criteria config to createBadge mutation

## Validation Layers

**1. Frontend Validation:**
- Required field checks
- Type validation (number, text, boolean)
- Range validation (min/max values)
- Allowed values validation
- Real-time error display

**2. GraphQL Mutation Validation:**
- Registry validation before database operations
- Returns user-friendly error messages
- Prevents invalid configs from reaching database

**3. Django Model Validation:**
- `Badge.clean()` validates criteria_config on save
- Ensures auto-awarded badges have valid config
- Validates scope compatibility

**4. Database Constraints:**
- Unique constraints on UserBadge
- Foreign key constraints ensure referential integrity

## Testing

**Backend Tests (`opencontractserver/tests/test_badges.py`):**
- 35 tests covering models, GraphQL, auto-awards, permissions
- Use `instance._skip_signals = True` to prevent signal interference
- Tests validate multi-layer validation works correctly

**Key Test Patterns:**
```python
# Prevent automatic badge awards in tests
msg = ChatMessage(conversation=conv, content="Test", creator=user)
msg._skip_signals = True
msg.save()

# Test validation errors
with self.assertRaises(ValidationError) as cm:
    Badge.objects.create(..., criteria_config={"invalid": "config"})
self.assertIn("criteria_config", cm.exception.message_dict)
```

## Architecture Notes

**Why Registry Pattern?**
- Single source of truth for criteria definitions
- Frontend UI adapts automatically to backend changes
- Type-safe validation
- Self-documenting (descriptions in registry)
- Easy to add new criteria types

**Why Multi-Layer Validation?**
- Frontend: Fast feedback, better UX
- GraphQL: Prevent invalid API calls
- Model: Ensure database integrity
- Database: Final safety net

**Why Signals?**
- Automatic badge awards without manual task calls
- Decoupled from core business logic
- Can be disabled for testing with `_skip_signals`

## File Locations

**Backend:**
- Models: `opencontractserver/badges/models.py`
- Registry: `opencontractserver/badges/criteria_registry.py`
- Tasks: `opencontractserver/tasks/badge_tasks.py`
- Signals: `opencontractserver/badges/signals.py`
- GraphQL Types: `config/graphql/graphene_types.py`
- GraphQL Queries: `config/graphql/queries.py`
- GraphQL Mutations: `config/graphql/badge_mutations.py`
- Default Badges Migration: `opencontractserver/badges/migrations/0005_install_default_badges.py`
- Tests: `opencontractserver/tests/test_badges.py`

**Frontend:**
- Badge Component: `frontend/src/components/badges/Badge.tsx`
- Management UI: `frontend/src/components/badges/BadgeManagement.tsx`
- Criteria Config: `frontend/src/components/badges/BadgeCriteriaConfig.tsx`
- GraphQL Queries: `frontend/src/graphql/queries.ts`
- GraphQL Mutations: `frontend/src/graphql/mutations.ts`
