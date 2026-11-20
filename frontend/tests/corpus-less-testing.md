# Corpus-less Testing Documentation

## Overview

This document describes the testing approach for the corpus-less mode of DocumentKnowledgeBase component, which allows viewing documents without corpus membership.

## Test Files

### 1. DocumentKnowledgeBaseCorpusless.ct.tsx

Main test file containing comprehensive test cases for corpus-less functionality:

- Document rendering without corpus
- Feature availability checks
- Annotation prevention
- Add to corpus flow
- Error handling
- UI state verification

### 2. DocumentKnowledgeBaseCorpuslessTestWrapper.tsx

Test wrapper that provides:

- Apollo MockedProvider setup
- Authentication state configuration
- Optional corpusId parameter for testing both modes
- Custom Apollo link for request logging

### 3. useFeatureAvailability.test.ts

Unit tests for the feature availability hook logic.

## Key Test Scenarios

### Without Corpus (corpusId undefined)

1. **Document Viewing**

   - Document renders successfully
   - PDF and text views work
   - Basic navigation functions

2. **Feature Restrictions**

   - Chat feature is hidden
   - Annotations are disabled
   - Extract tools are hidden
   - Export requires corpus

3. **UI Indicators**

   - Corpus-less banner shows
   - "Add to Corpus" CTA is visible
   - Feature unavailable states display correctly

4. **User Actions**
   - Text selection doesn't create annotations
   - Add to corpus modal opens
   - Corpus selection works

### With Corpus (corpusId provided)

1. **Full Features**

   - All features are available
   - Annotations can be created
   - Chat is accessible
   - Extract tools show

2. **UI State**
   - No corpus-less banner
   - Full annotation tools visible
   - All floating controls enabled

## Running Tests

```bash
# Run all component tests
npm run test:ct

# Run corpus-less tests specifically
npm run test:ct -- DocumentKnowledgeBaseCorpusless

# Run in UI mode for debugging
npm run test:ct:ui
```

## Mock Data Structure

### Document Mock

```typescript
const mockDocument = {
  id: "doc-123",
  title: "Test Document",
  fileType: "application/pdf",
  pdfFile: "http://localhost/test.pdf",
  txtFile: "http://localhost/test.txt",
  totalPageCount: 10,
  corpusAssignments: { edges: [] },
};
```

### Corpus Mock

```typescript
const mockCorpus = {
  id: "corpus-1",
  title: "Test Corpus",
  myPermissions: ["read", "write", "create"],
  labelSet: {/* label configuration */},
};
```

## GraphQL Queries Used

1. **GET_DOCUMENT_ONLY** - Fetches document without corpus data
2. **GET_DOCUMENT_KNOWLEDGE_AND_ANNOTATIONS** - Full document with annotations
3. **GET_MY_CORPUSES** - Lists user's available corpuses
4. **ADD_DOCUMENT_TO_CORPUS** - Mutation to add document to corpus

## Best Practices

1. **Test Isolation**

   - Each test should be independent
   - Use fresh mocks for each scenario
   - Clean up state between tests

2. **Mock Management**

   - Keep mocks minimal but complete
   - Match actual GraphQL response structure
   - Use consistent test data

3. **Assertion Strategy**

   - Test visible UI changes
   - Verify feature availability
   - Check error states
   - Validate user interactions

4. **Performance**
   - Use data-testid for reliable selectors
   - Minimize wait times
   - Test only essential flows

## Debugging Tips

1. **Console Logging**

   - Test wrapper logs GraphQL requests/responses
   - Check browser console in headed mode

2. **Visual Debugging**

   ```bash
   # Run tests in headed mode
   npm run test:ct -- --headed
   ```

3. **Specific Test**
   ```bash
   # Run single test
   npm run test:ct -- -g "should render document without corpus"
   ```

## Future Enhancements

1. Add tests for:

   - Keyboard navigation in corpus-less mode
   - Mobile responsive behavior
   - Performance with large documents
   - Multiple document handling

2. Consider testing:
   - Real-time corpus assignment updates
   - Permission changes during session
   - Network error recovery
