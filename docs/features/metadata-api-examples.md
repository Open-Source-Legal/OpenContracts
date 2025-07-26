# Metadata API Examples

This document provides practical examples of using the unified metadata fields API in OpenContracts.

**Important Note on Field Naming**: OpenContracts uses Graphene Django which automatically converts Python `snake_case` field names to GraphQL `camelCase`. Throughout this document:
- `data_type` (model field) appears as `dataType` (GraphQL field)
- `validation_config` (model field) appears as `validationConfig` (GraphQL field)  
- `is_manual_entry` (model field) appears as `isManualEntry` (GraphQL field)
- `default_value` (model field) appears as `defaultValue` (GraphQL field)

## Architecture Overview

OpenContracts uses a **unified data model** for both extracted data and manual metadata entry:

- **Columns** define the schema for metadata fields within a corpus
- **Datacells** store the actual metadata values for each document
- **Fieldsets** organize columns and are automatically created for each corpus
- **Validation** is performed based on data type and validation rules

This unified approach eliminates code duplication and provides consistent handling of structured data throughout the application.

### Key Concepts

- **Corpus-Level Schema**: Metadata columns are defined at the corpus level, not in labelsets
- **Manual Entry Flag**: Columns have an `isManualEntry` flag to distinguish metadata from extracted data  
- **Unified Permissions**: Metadata access is controlled by corpus permissions
- **Data Types**: Support for STRING, TEXT, BOOLEAN, INTEGER, FLOAT, DATE, DATETIME, URL, EMAIL, CHOICE, MULTI_CHOICE, and JSON

## Complete Workflow Examples

### 1. Setting Up a Contract Management Corpus

This example shows how to create a complete metadata schema for managing contracts.

```graphql
# Step 1: Create the corpus (fieldset is automatically created)
mutation CreateContractCorpus {
  createCorpus(
    title: "2024 Vendor Contracts"
    description: "All vendor contracts for fiscal year 2024"
  ) {
    ok
    obj {
      id
      title
    }
  }
}

# Step 2: Add metadata columns to the corpus
# Assuming corpusId: "Q29ycHVzVHlwZTo3ODk="

# Add contract type field (choice)
mutation AddContractType {
  createMetadataColumn(
    corpusId: "Q29ycHVzVHlwZTo3ODk=",
    name: "Contract Type",
    dataType: "CHOICE",
    helpText: "Type of vendor contract",
    validationConfig: {
      required: true,
      choices: ["Service Agreement", "Purchase Order", "NDA", "License Agreement", "Other"],
      default_value: "Service Agreement"
    }
  ) {
    ok
    obj {
      id
      name
      dataType
      isManualEntry
    }
  }
}

# Add vendor name field (string with validation)
mutation AddVendorName {
  createMetadataColumn(
    corpusId: "Q29ycHVzVHlwZTo3ODk=",
    name: "Vendor Name",
    dataType: "STRING",
    helpText: "Legal name of the vendor/supplier",
    validationConfig: {
      required: true,
      min_length: 2,
      max_length: 200
    }
  ) {
    ok
    obj {
      id
      name
    }
  }
}

# Add contract value field (float with range)
mutation AddContractValue {
  createMetadataColumn(
    corpusId: "Q29ycHVzVHlwZTo3ODk=",
    name: "Contract Value",
    dataType: "FLOAT",
    helpText: "Total contract value in USD",
    validationConfig: {
      required: true,
      min_value: 0,
      max_value: 10000000
    }
  ) {
    ok
    obj {
      id
      name
    }
  }
}

# Add start date field
mutation AddStartDate {
  createMetadataColumn(
    corpusId: "Q29ycHVzVHlwZTo3ODk=",
    name: "Start Date",
    dataType: "DATE",
    helpText: "Contract effective start date",
    validationConfig: {
      required: true
    }
  ) {
    ok
    obj {
      id
      name
    }
  }
}

# Add end date field (optional)
mutation AddEndDate {
  createMetadataColumn(
    corpusId: "Q29ycHVzVHlwZTo3ODk=",
    name: "End Date",
    dataType: "DATE",
    helpText: "Contract expiration date (leave blank for perpetual contracts)",
    validationConfig: {
      required: false
    }
  ) {
    ok
    obj {
      id
      name
    }
  }
}

# Add auto-renewal field (boolean)
mutation AddAutoRenewal {
  createMetadataColumn(
    corpusId: "Q29ycHVzVHlwZTo3ODk=",
    name: "Auto-Renewal",
    dataType: "BOOLEAN",
    helpText: "Does this contract automatically renew?",
    validationConfig: {
      required: true,
      default_value: false
    }
  ) {
    ok
    obj {
      id
      name
    }
  }
}

# Add departments field (multi-choice)
mutation AddDepartments {
  createMetadataColumn(
    corpusId: "Q29ycHVzVHlwZTo3ODk=",
    name: "Departments",
    dataType: "MULTI_CHOICE",
    helpText: "Departments affected by this contract",
    validationConfig: {
      required: true,
      choices: ["IT", "HR", "Finance", "Operations", "Legal", "Marketing", "Sales"]
    }
  ) {
    ok
    obj {
      id
      name
    }
  }
}

# Add contract status field
mutation AddContractStatus {
  createMetadataColumn(
    corpusId: "Q29ycHVzVHlwZTo3ODk=",
    name: "Status",
    dataType: "CHOICE",
    helpText: "Current status in the contract lifecycle",
    validationConfig: {
      required: true,
      choices: ["Draft", "Under Review", "Approved", "Active", "Expired", "Terminated"],
      default_value: "Draft"
    }
  ) {
    ok
    obj {
      id
      name
    }
  }
}

# Add notes field (text)
mutation AddNotes {
  createMetadataColumn(
    corpusId: "Q29ycHVzVHlwZTo3ODk=",
    name: "Notes",
    dataType: "TEXT",
    helpText: "Additional notes or comments about this contract",
    validationConfig: {
      required: false,
      max_length: 5000
    }
  ) {
    ok
    obj {
      id
      name
    }
  }
}
```

### 2. Setting Metadata Values for a Document

```graphql
# After uploading a contract document, set its metadata values
# Assume documentId: "RG9jdW1lbnRUeXBlOjQ1Ng=="
# Column IDs from the mutations above

# Set contract type
mutation SetContractType {
  setMetadataValue(
    documentId: "RG9jdW1lbnRUeXBlOjQ1Ng==",
    corpusId: "Q29ycHVzVHlwZTo3ODk=",
    columnId: "Q29sdW1uVHlwZToxMDE=",
    value: "Service Agreement"
  ) {
    ok
    message
    obj {
      id
      data
    }
  }
}

# Set vendor name
mutation SetVendorName {
  setMetadataValue(
    documentId: "RG9jdW1lbnRUeXBlOjQ1Ng==",
    corpusId: "Q29ycHVzVHlwZTo3ODk=",
    columnId: "Q29sdW1uVHlwZToxMDI=",
    value: "Acme Software Solutions Inc."
  ) {
    ok
    message
    obj {
      id
      data
    }
  }
}

# Set contract value
mutation SetContractValue {
  setMetadataValue(
    documentId: "RG9jdW1lbnRUeXBlOjQ1Ng==",
    corpusId: "Q29ycHVzVHlwZTo3ODk=",
    columnId: "Q29sdW1uVHlwZToxMDM=",
    value: 75000.00
  ) {
    ok
    message
    obj {
      id
      data
    }
  }
}

# Set multiple values in one mutation
mutation SetContractDates {
  startDate: setMetadataValue(
    documentId: "RG9jdW1lbnRUeXBlOjQ1Ng==",
    columnId: "Q29sdW1uVHlwZToxMDQ=",
    value: "2024-01-01"
  ) {
    ok
    obj { id }
  }
  
  endDate: setMetadataValue(
    documentId: "RG9jdW1lbnRUeXBlOjQ1Ng==",
    columnId: "Q29sdW1uVHlwZToxMDU=",
    value: "2024-12-31"
  ) {
    ok
    obj { id }
  }
}

# Set boolean value
mutation SetAutoRenewal {
  setMetadataValue(
    documentId: "RG9jdW1lbnRUeXBlOjQ1Ng==",
    columnId: "Q29sdW1uVHlwZToxMDY=",
    value: true
  ) {
    ok
    obj {
      id
      data
    }
  }
}

# Set multi-choice value (array)
mutation SetDepartments {
  setMetadataValue(
    documentId: "RG9jdW1lbnRUeXBlOjQ1Ng==",
    columnId: "Q29sdW1uVHlwZToxMDc=",
    value: ["IT", "Operations"]
  ) {
    ok
    obj {
      id
      data
    }
  }
}

# Set status
mutation SetStatus {
  setMetadataValue(
    documentId: "RG9jdW1lbnRUeXBlOjQ1Ng==",
    columnId: "Q29sdW1uVHlwZToxMDg=",
    value: "Active"
  ) {
    ok
    obj {
      id
      data
    }
  }
}
```

### 3. Querying Metadata Schema and Values

```graphql
# Get all metadata columns for a corpus (schema)
query GetCorpusMetadataSchema {
  corpusMetadataColumns(corpusId: "Q29ycHVzVHlwZTo3ODk=") {
    id
    name
    dataType
    helpText
    validationConfig
    defaultValue
    displayOrder
    isManualEntry
    outputType
    taskName
  }
}

# Get all metadata values for a specific document
query GetDocumentMetadata {
  documentMetadataDatacells(
    documentId: "RG9jdW1lbnRUeXBlOjQ1Ng==",
    corpusId: "Q29ycHVzVHlwZTo3ODk="
  ) {
    id
    data
    dataDefinition
    column {
      id
      name
      dataType
      helpText
      validationConfig
      isManualEntry
    }
    creator {
      id
      email
    }
  }
}

# Check metadata completion status
query CheckMetadataCompletion {
  metadataCompletionStatusV2(
    documentId: "RG9jdW1lbnRUeXBlOjQ1Ng==",
    corpusId: "Q29ycHVzVHlwZTo3ODk="
  ) {
    totalFields
    filledFields
    missingFields
    percentage
    missingRequired
  }
}
```

### 4. Updating and Managing Metadata

```graphql
# Update an existing metadata column
mutation UpdateContractTypeChoices {
  updateMetadataColumn(
    columnId: "Q29sdW1uVHlwZToxMDE=",
    name: "Contract Type",
    validationConfig: {
      required: true,
      choices: ["Service Agreement", "Purchase Order", "NDA", "License Agreement", "Consulting Agreement", "Other"],
      default_value: "Service Agreement"
    }
  ) {
    ok
    obj {
      id
      name
      validationConfig
    }
  }
}

# Delete a metadata value
mutation RemoveMetadataValue {
  deleteMetadataValue(
    documentId: "RG9jdW1lbnRUeXBlOjQ1Ng==",
    corpusId: "Q29ycHVzVHlwZTo3ODk=",
    columnId: "Q29sdW1uVHlwZToxMDE="
  ) {
    ok
    message
  }
}

# Update an existing metadata value
mutation UpdateContractValue {
  setMetadataValue(
    documentId: "RG9jdW1lbnRUeXBlOjQ1Ng==",
    columnId: "Q29sdW1uVHlwZToxMDM=",
    value: 85000.00
  ) {
    ok
    obj {
      id
      data
    }
  }
}
```

### 5. Advanced Use Cases

#### Email Field with Validation

```graphql
mutation AddContactEmail {
  createMetadataColumn(
    corpusId: "Q29ycHVzVHlwZTo3ODk=",
    name: "Contact Email",
    dataType: "EMAIL",
    helpText: "Primary contact email for this contract",
    validationConfig: {
      required: true
    }
  ) {
    ok
    obj {
      id
      name
    }
  }
}
```

#### URL Field

```graphql
mutation AddContractURL {
  createMetadataColumn(
    corpusId: "Q29ycHVzVHlwZTo3ODk=",
    name: "Contract Portal URL",
    dataType: "URL",
    helpText: "Link to vendor's contract management portal",
    validationConfig: {
      required: false
    }
  ) {
    ok
    obj {
      id
      name
    }
  }
}
```

#### Custom Validation with Regex

```graphql
mutation AddContractNumber {
  createMetadataColumn(
    corpusId: "Q29ycHVzVHlwZTo3ODk=",
    name: "Contract Number",
    dataType: "STRING",
    helpText: "Unique contract identifier (Format: XX-YYYY-NNNNNN)",
    validationConfig: {
      required: true,
      regex_pattern: "^[A-Z]{2}-\\d{4}-\\d{6}$"
    }
  ) {
    ok
    obj {
      id
      name
    }
  }
}
```

#### Complex JSON Metadata

```graphql
mutation AddRenewalTerms {
  createMetadataColumn(
    corpusId: "Q29ycHVzVHlwZTo3ODk=",
    name: "Renewal Terms",
    dataType: "JSON",
    helpText: "Detailed renewal terms and conditions",
    validationConfig: {
      required: false
    }
  ) {
    ok
    obj {
      id
      name
    }
  }
}

# Set complex JSON data
mutation SetRenewalTerms {
  setMetadataValue(
    documentId: "RG9jdW1lbnRUeXBlOjQ1Ng==",
    columnId: "Q29sdW1uVHlwZToxMTA=",
    value: {
      "notice_period_days": 90,
      "automatic_renewal": true,
      "renewal_term_months": 12,
      "price_adjustment": {
        "type": "percentage",
        "value": 3,
        "basis": "CPI"
      },
      "opt_out_window": {
        "start_days_before": 120,
        "end_days_before": 90
      }
    }
  ) {
    ok
    obj {
      id
      data
    }
  }
}
```

#### Date and DateTime Fields

```graphql
mutation AddSignatureDate {
  createMetadataColumn(
    corpusId: "Q29ycHVzVHlwZTo3ODk=",
    name: "Signature Date",
    dataType: "DATE",
    helpText: "Date when contract was signed",
    validationConfig: {
      required: true
    }
  ) {
    ok
    obj { id }
  }
}

mutation AddLastReviewTimestamp {
  createMetadataColumn(
    corpusId: "Q29ycHVzVHlwZTo3ODk=",
    name: "Last Review",
    dataType: "DATETIME",
    helpText: "Timestamp of last contract review",
    validationConfig: {
      required: false
    }
  ) {
    ok
    obj { id }
  }
}
```

#### Bulk Operations

```graphql
# Bulk update multiple documents' status
mutation BulkUpdateStatus {
  doc1: setMetadataValue(
    documentId: "RG9jdW1lbnRUeXBlOjQ1Ng==",
    columnId: "Q29sdW1uVHlwZToxMDg=",
    value: "Expired"
  ) { ok }
  
  doc2: setMetadataValue(
    documentId: "RG9jdW1lbnRUeXBlOjQ1Nw==",
    columnId: "Q29sdW1uVHlwZToxMDg=",
    value: "Expired"
  ) { ok }
  
  doc3: setMetadataValue(
    documentId: "RG9jdW1lbnRUeXBlOjQ1OA==",
    columnId: "Q29sdW1uVHlwZToxMDg=",
    value: "Expired"
  ) { ok }
}
```

## Error Handling Examples

### Validation Errors

```graphql
# Example: Invalid email format
mutation SetInvalidEmail {
  setMetadataValue(
    documentId: "RG9jdW1lbnRUeXBlOjQ1Ng==",
    columnId: "Q29sdW1uVHlwZToyMDE=",
    value: "not-an-email"
  ) {
    ok
    message  # Will contain validation error details
  }
}

# Example: Value out of range
mutation SetInvalidValue {
  setMetadataValue(
    documentId: "RG9jdW1lbnRUeXBlOjQ1Ng==",
    columnId: "Q29sdW1uVHlwZToxMDM=",
    value: -1000
  ) {
    ok
    message  # Will contain: "Value must be at least 0"
  }
}

# Example: Invalid choice
mutation SetInvalidChoice {
  setMetadataValue(
    documentId: "RG9jdW1lbnRUeXBlOjQ1Ng==",
    columnId: "Q29sdW1uVHlwZToxMDE=",
    value: "Invalid Type"
  ) {
    ok
    message  # Will contain available choices
  }
}

# Example: Required field missing
mutation SetEmptyRequired {
  setMetadataValue(
    documentId: "RG9jdW1lbnRUeXBlOjQ1Ng==",
    columnId: "Q29sdW1uVHlwZToxMDI=",
    value: ""
  ) {
    ok
    message  # Will contain: "This field is required"
  }
}
```

## Integration Patterns

### React Component Example

```typescript
import { useQuery, useMutation } from '@apollo/client';
import { gql } from '@apollo/client';

const GET_CORPUS_METADATA_COLUMNS = gql`
  query GetCorpusMetadataColumns($corpusId: ID!) {
    corpusMetadataColumns(corpusId: $corpusId) {
      id
      name
      dataType
      helpText
      validationConfig
      defaultValue
      isManualEntry
    }
  }
`;

const GET_DOCUMENT_METADATA_DATACELLS = gql`
  query GetDocumentMetadataDatacells($documentId: ID!, $corpusId: ID!) {
    documentMetadataDatacells(documentId: $documentId, corpusId: $corpusId) {
      id
      data
      column {
        id
        name
        dataType
        validationConfig
      }
    }
  }
`;

const SET_METADATA_VALUE = gql`
  mutation SetMetadataValue($documentId: ID!, $corpusId: ID!, $columnId: ID!, $value: GenericScalar!) {
    setMetadataValue(documentId: $documentId, corpusId: $corpusId, columnId: $columnId, value: $value) {
      ok
      message
      obj {
        id
        data
      }
    }
  }
`;

interface MetadataFormProps {
  documentId: string;
  corpusId: string;
}

export const MetadataForm: React.FC<MetadataFormProps> = ({ documentId, corpusId }) => {
  // Fetch metadata schema
  const { data: schemaData } = useQuery(GET_CORPUS_METADATA_COLUMNS, {
    variables: { corpusId }
  });

  // Fetch current values
  const { data: valuesData } = useQuery(GET_DOCUMENT_METADATA_DATACELLS, {
    variables: { documentId, corpusId }
  });

  // Update mutation
  const [setMetadataValue] = useMutation(SET_METADATA_VALUE);

  const handleMetadataChange = async (columnId: string, value: any) => {
    try {
      const result = await setMetadataValue({
        variables: {
          documentId,
          corpusId,
          columnId,
          value
        }
      });

      if (!result.data.setMetadataValue.ok) {
        toast.error(result.data.setMetadataValue.message);
      } else {
        toast.success('Metadata updated successfully');
      }
    } catch (error) {
      toast.error('Failed to update metadata');
      console.error(error);
    }
  };

  const columns = schemaData?.corpusMetadataColumns || [];
  const values = valuesData?.documentMetadataDatacells || [];

  // Create a map of column ID to current value
  const valueMap = new Map(
    values.map(datacell => [datacell.column.id, datacell.data])
  );

  return (
    <div className="metadata-form">
      {columns.map(column => (
        <MetadataField
          key={column.id}
          column={column}
          value={valueMap.get(column.id)}
          onChange={(value) => handleMetadataChange(column.id, value)}
        />
      ))}
    </div>
  );
};
```

### Python Script Example

```python
import requests
import json
from typing import Dict, List, Any, Optional

class OpenContractsMetadataClient:
    def __init__(self, api_url: str, auth_token: str):
        self.api_url = api_url
        self.headers = {
            'Authorization': f'Bearer {auth_token}',
            'Content-Type': 'application/json'
        }
    
    def create_metadata_column(self, corpus_id: str, name: str, data_type: str, 
                             validation_config: Optional[Dict] = None, 
                             help_text: Optional[str] = None) -> Dict:
        """Create a new metadata column in a corpus."""
        query = """
        mutation CreateMetadataColumn(
            $corpusId: ID!,
            $name: String!,
            $dataType: String!,
            $validationConfig: GenericScalar,
            $helpText: String
        ) {
            createMetadataColumn(
                corpusId: $corpusId,
                name: $name,
                dataType: $dataType,
                validationConfig: $validationConfig,
                helpText: $helpText
            ) {
                ok
                message
                obj {
                    id
                    name
                    dataType
                    isManualEntry
                }
            }
        }
        """
        
        variables = {
            'corpusId': corpus_id,
            'name': name,
            'dataType': data_type
        }
        
        if validation_config:
            variables['validationConfig'] = validation_config
        if help_text:
            variables['helpText'] = help_text
        
        response = requests.post(
            self.api_url,
            headers=self.headers,
            json={'query': query, 'variables': variables}
        )
        
        return response.json()
    
    def set_metadata_value(self, document_id: str, corpus_id: str, column_id: str, value: Any) -> Dict:
        """Set a metadata value for a document."""
        query = """
        mutation SetMetadataValue($documentId: ID!, $corpusId: ID!, $columnId: ID!, $value: GenericScalar!) {
            setMetadataValue(documentId: $documentId, corpusId: $corpusId, columnId: $columnId, value: $value) {
                ok
                message
                obj {
                    id
                    data
                }
            }
        }
        """
        
        response = requests.post(
            self.api_url,
            headers=self.headers,
            json={
                'query': query,
                'variables': {
                    'documentId': document_id,
                    'corpusId': corpus_id,
                    'columnId': column_id,
                    'value': value
                }
            }
        )
        
        return response.json()
    
    def get_corpus_metadata_schema(self, corpus_id: str) -> List[Dict]:
        """Get all metadata columns for a corpus."""
        query = """
        query GetCorpusMetadataColumns($corpusId: ID!) {
            corpusMetadataColumns(corpusId: $corpusId) {
                id
                name
                dataType
                helpText
                validationConfig
                defaultValue
                isManualEntry
            }
        }
        """
        
        response = requests.post(
            self.api_url,
            headers=self.headers,
            json={
                'query': query,
                'variables': {'corpusId': corpus_id}
            }
        )
        
        result = response.json()
        return result.get('data', {}).get('corpusMetadataColumns', [])
    
    def get_document_metadata(self, document_id: str, corpus_id: str) -> List[Dict]:
        """Get all metadata values for a document."""
        query = """
        query GetDocumentMetadataDatacells($documentId: ID!, $corpusId: ID!) {
            documentMetadataDatacells(documentId: $documentId, corpusId: $corpusId) {
                id
                data
                column {
                    id
                    name
                    dataType
                    validationConfig
                }
            }
        }
        """
        
        response = requests.post(
            self.api_url,
            headers=self.headers,
            json={
                'query': query,
                'variables': {
                    'documentId': document_id,
                    'corpusId': corpus_id
                }
            }
        )
        
        result = response.json()
        return result.get('data', {}).get('documentMetadataDatacells', [])
    
    def bulk_set_metadata_values(self, updates: List[Dict]) -> Dict:
        """Set metadata values for multiple documents."""
        operations = []
        
        for i, update in enumerate(updates):
            operations.append(f"""
                update{i}: setMetadataValue(
                    documentId: "{update['documentId']}",
                    columnId: "{update['columnId']}",
                    value: {json.dumps(update['value'])}
                ) {{
                    ok
                    message
                }}
            """)
        
        query = f"mutation BulkUpdate {{ {' '.join(operations)} }}"
        
        response = requests.post(
            self.api_url,
            headers=self.headers,
            json={'query': query}
        )
        
        return response.json()

# Usage example
if __name__ == "__main__":
    client = OpenContractsMetadataClient(
        api_url="https://your-opencontracts-instance.com/graphql/",
        auth_token="your-auth-token"
    )
    
    # Create a contract type field
    result = client.create_metadata_column(
        corpus_id="Q29ycHVzVHlwZTo3ODk=",
        name="Contract Type",
        data_type="CHOICE",
        validation_config={
            "required": True,
            "choices": ["Service Agreement", "Purchase Order", "NDA"],
            "default_value": "Service Agreement"
        },
        help_text="Type of vendor contract"
    )
    
    if result.get('data', {}).get('createMetadataColumn', {}).get('ok'):
        column_id = result['data']['createMetadataColumn']['obj']['id']
        print(f"Created column with ID: {column_id}")
        
        # Set a value for this field
        value_result = client.set_metadata_value(
            document_id="RG9jdW1lbnRUeXBlOjQ1Ng==",
            corpus_id="Q29ycHVzVHlwZTo3ODk=",
            column_id=column_id,
            value="Service Agreement"
        )
        
        if value_result.get('data', {}).get('setMetadataValue', {}).get('ok'):
            print("Successfully set metadata value")
        else:
            print("Failed to set value:", value_result)
    else:
        print("Failed to create column:", result)
```

## Data Type Reference

### Available Data Types

| Type | Description | Example Values | Validation Options |
|------|-------------|----------------|-------------------|
| `STRING` | Short text | "Acme Corp" | `min_length`, `max_length`, `regex_pattern` |
| `TEXT` | Long text | "Contract notes..." | `min_length`, `max_length` |
| `BOOLEAN` | True/false | `true`, `false` | `default_value` |
| `INTEGER` | Whole numbers | `42`, `1000` | `min_value`, `max_value` |
| `FLOAT` | Decimal numbers | `1234.56`, `0.5` | `min_value`, `max_value` |
| `DATE` | Date only | `"2024-01-15"` | None |
| `DATETIME` | Date and time | `"2024-01-15T10:30:00Z"` | None |
| `URL` | Web addresses | `"https://example.com"` | None |
| `EMAIL` | Email addresses | `"user@example.com"` | None |
| `CHOICE` | Single selection | `"Option A"` | `choices`, `default_value` |
| `MULTI_CHOICE` | Multiple selections | `["Option A", "Option B"]` | `choices` |
| `JSON` | Complex data | `{"key": "value"}` | None |

### Validation Configuration Options

```typescript
interface ValidationConfig {
  required?: boolean;           // Field is required
  default_value?: any;          // Default value
  min_length?: number;          // Minimum string length
  max_length?: number;          // Maximum string length
  min_value?: number;           // Minimum numeric value
  max_value?: number;           // Maximum numeric value
  regex_pattern?: string;       // Regular expression pattern
  choices?: string[];           // Available choices for CHOICE/MULTI_CHOICE
  help_text?: string;           // Additional help text
}
```

## Best Practices

### 1. Schema Design

- **Use descriptive names**: Make column names clear and unambiguous
- **Set appropriate defaults**: Provide sensible default values for required fields
- **Include help text**: Add helpful descriptions for complex fields
- **Order thoughtfully**: Use `displayOrder` to control field presentation

### 2. Data Types

- **STRING vs TEXT**: Use STRING for short values (< 255 chars), TEXT for longer content
- **CHOICE vs MULTI_CHOICE**: Use CHOICE for single selections, MULTI_CHOICE for multiple
- **Date formats**: Always use ISO format (YYYY-MM-DD) for dates
- **JSON validation**: Consider the complexity of JSON structures for user experience

### 3. Validation

- **Be specific with constraints**: Set appropriate min/max values and lengths
- **Use regex sparingly**: Only when necessary, and include clear help text
- **Required vs optional**: Carefully consider which fields should be required

### 4. Performance

- **Batch operations**: Use bulk mutations for updating multiple documents
- **Selective queries**: Only query the fields you need
- **Cache schema**: Metadata schemas change infrequently, cache them appropriately

### 5. Error Handling

- **Check `ok` field**: Always verify mutation success before proceeding
- **Display validation errors**: Show clear error messages to users
- **Graceful degradation**: Handle missing or invalid data appropriately