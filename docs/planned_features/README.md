# Planned Features

This directory contains detailed specifications and implementation plans for upcoming features in OpenContracts.

## Feature List

### [Metadata Field Management](./metadata-field-management.md)
**Status**: Planning Phase  
**Priority**: High  
**Estimated Timeline**: 5 weeks

Comprehensive metadata management system allowing users to:
- Define custom metadata schemas at the corpus level
- Edit metadata values inline using an Excel-like grid interface
- Filter and search documents by metadata values
- Configure validation rules and data types for metadata fields

The implementation leverages the existing unified Column/Datacell architecture that powers the data extraction features, ensuring consistency and code reuse throughout the application.

---

## Contributing

When adding a new planned feature:
1. Create a detailed specification document following the format of existing plans
2. Include clear success metrics and timelines
3. Add an entry to this README with status and brief description
4. Consider dependencies and integration with existing features