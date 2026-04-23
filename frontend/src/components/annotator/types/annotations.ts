import { v4 as uuidv4 } from "uuid";
import { AnnotationLabelType } from "../../../types/graphql-api";
import {
  CompactAnnotationJson,
  expandAnnotationJson,
  isSpanFormat,
} from "../../../utils/compactAnnotationJson";
import {
  SpanAnnotationJson,
  PermissionTypes,
  MultipageAnnotationJson,
} from "../../types";

export interface TokenId {
  pageIndex: number;
  tokenIndex: number;
}

export type BoundingBox = {
  top: number;
  bottom: number;
  left: number;
  right: number;
};

export class RelationGroup {
  constructor(
    public sourceIds: string[],
    public targetIds: string[],
    public label: AnnotationLabelType,
    public id: string = uuidv4(),
    public structural: boolean = false
  ) {
    this.id = id;
  }

  // NOTE: Relation deletions triggered by annotation removal are not currently
  // reflected in the undo/redo log. This is acceptable because undo operates
  // on the annotations array directly, and orphaned relations are pruned.
  updateForAnnotationDeletion(
    a: ServerTokenAnnotation | ServerSpanAnnotation
  ): RelationGroup | undefined {
    const newSourceIds = this.sourceIds.filter((id) => id !== a.id);
    const newTargetIds = this.targetIds.filter((id) => id !== a.id);

    // A relation requires at least one source and one target; if either side
    // is empty after pruning, the relation is orphaned and must be dropped.
    if (newSourceIds.length === 0 || newTargetIds.length === 0) {
      return undefined;
    }

    // Preserve id/structural so surviving relation stays the same entity.
    return new RelationGroup(
      newSourceIds,
      newTargetIds,
      this.label,
      this.id,
      this.structural
    );
  }

  static fromObject(obj: RelationGroup) {
    return new RelationGroup(
      obj.sourceIds,
      obj.targetIds,
      obj.label,
      obj.id,
      obj.structural
    );
  }
}

export class ServerSpanAnnotation {
  public readonly id: string;

  constructor(
    public readonly page: number,
    public readonly annotationLabel: AnnotationLabelType,
    public readonly rawText: string,
    public readonly structural: boolean,
    public readonly json: SpanAnnotationJson,
    public readonly myPermissions: PermissionTypes[],
    public readonly approved: boolean,
    public readonly rejected: boolean,
    public readonly canComment: boolean = false,
    id: string | undefined = undefined,
    public readonly contentModalities?: string[]
  ) {
    this.id = id || uuidv4();
  }

  toString() {
    return this.id;
  }

  update(delta: Partial<ServerSpanAnnotation> = {}): ServerSpanAnnotation {
    return new ServerSpanAnnotation(
      delta.page ?? this.page,
      delta.annotationLabel ?? Object.assign({}, this.annotationLabel),
      delta.rawText ?? this.rawText,
      delta.structural ?? this.structural,
      delta.json ?? this.json,
      delta.myPermissions ?? this.myPermissions,
      delta.approved ?? this.approved,
      delta.rejected ?? this.rejected,
      delta.canComment ?? this.canComment,
      this.id,
      delta.contentModalities ?? this.contentModalities
    );
  }

  static fromObject(obj: ServerSpanAnnotation): ServerSpanAnnotation {
    return new ServerSpanAnnotation(
      obj.page,
      obj.annotationLabel,
      obj.rawText,
      obj.structural,
      obj.json,
      obj.myPermissions,
      obj.approved,
      obj.rejected,
      obj.canComment,
      obj.id,
      obj.contentModalities
    );
  }
}

export class ServerTokenAnnotation {
  public readonly id: string;
  public readonly json: MultipageAnnotationJson;

  constructor(
    public readonly page: number,
    public readonly annotationLabel: AnnotationLabelType,
    public readonly rawText: string,
    public readonly structural: boolean,
    json:
      | MultipageAnnotationJson
      | CompactAnnotationJson
      | Record<string, unknown>,
    public readonly myPermissions: PermissionTypes[],
    public readonly approved: boolean,
    public readonly rejected: boolean,
    public readonly canComment: boolean = false,
    id: string | undefined = undefined,
    public readonly contentModalities?: string[]
  ) {
    this.id = id || uuidv4();
    // Normalize any format (v1 or v2) to v1 for the rendering layer.
    const record = json as Record<string, unknown>;
    if (json && typeof json === "object" && !isSpanFormat(record)) {
      const expanded = expandAnnotationJson(
        json as MultipageAnnotationJson | CompactAnnotationJson,
        rawText
      );
      this.json = (expanded ?? json) as MultipageAnnotationJson;
    } else {
      this.json = json as MultipageAnnotationJson;
    }
  }

  toString() {
    return this.id;
  }

  /**
   * Returns a deep copy of the provided Annotation with the applied
   * changes.
   */
  update(delta: Partial<ServerTokenAnnotation> = {}) {
    return new ServerTokenAnnotation(
      delta.page ?? this.page,
      delta.annotationLabel ?? Object.assign({}, this.annotationLabel),
      delta.rawText ?? this.rawText,
      delta.structural ?? this.structural,
      delta.json ?? this.json,
      delta.myPermissions ?? this.myPermissions,
      delta.approved ?? this.approved,
      delta.rejected ?? this.rejected,
      delta.canComment ?? this.canComment,
      this.id,
      delta.contentModalities ?? this.contentModalities
    );
  }

  static fromObject(obj: ServerTokenAnnotation) {
    return new ServerTokenAnnotation(
      obj.page,
      obj.annotationLabel,
      obj.rawText,
      obj.structural,
      obj.json,
      obj.myPermissions,
      obj.approved,
      obj.rejected,
      obj.canComment,
      obj.id,
      obj.contentModalities
    );
  }
}

/**
 * Union type covering both PDF token and text span annotations.
 */
export type ServerAnnotation = ServerTokenAnnotation | ServerSpanAnnotation;

export class RenderedSpanAnnotation {
  public readonly id: string;

  constructor(
    public bounds: BoundingBox,
    public readonly page: number,
    public readonly annotationLabel: AnnotationLabelType,
    public readonly tokens: TokenId[] | null = null,
    public readonly rawText: string,
    id: string | undefined = undefined
  ) {
    this.id = id || uuidv4();
  }

  toString() {
    return this.id;
  }

  /**
   * Returns a deep copy of the provided Annotation with the applied
   * changes.
   */
  update(delta: Partial<RenderedSpanAnnotation> = {}) {
    return new RenderedSpanAnnotation(
      delta.bounds ?? Object.assign({}, this.bounds),
      delta.page ?? this.page,
      delta.annotationLabel ?? Object.assign({}, this.annotationLabel),
      delta.tokens ?? this.tokens?.map((t) => Object.assign({}, t)),
      delta.rawText ?? this.rawText,
      this.id
    );
  }

  static fromObject(obj: RenderedSpanAnnotation) {
    return new RenderedSpanAnnotation(
      obj.bounds,
      obj.page,
      obj.annotationLabel,
      obj.tokens,
      obj.rawText,
      obj.id
    );
  }
}

export class DocTypeAnnotation {
  public readonly id: string;

  constructor(
    public readonly annotationLabel: AnnotationLabelType,
    public readonly myPermissions: PermissionTypes[],
    id: string | undefined = undefined
  ) {
    this.id = id || uuidv4();
  }

  toString() {
    return this.id;
  }

  static fromObject(obj: DocTypeAnnotation) {
    return new DocTypeAnnotation(
      obj.annotationLabel,
      obj.myPermissions,
      obj.id
    );
  }
}

export class PdfAnnotations {
  constructor(
    public readonly annotations: (
      | ServerTokenAnnotation
      | ServerSpanAnnotation
    )[],
    public readonly relations: RelationGroup[],
    public readonly docTypes: DocTypeAnnotation[],
    public readonly unsavedChanges: boolean = false
  ) {}

  saved(): PdfAnnotations {
    return new PdfAnnotations(
      this.annotations,
      this.relations,
      this.docTypes,
      false
    );
  }

  /** Remove the most recently added annotation and clean up any relations referencing it. */
  undoAnnotation(): PdfAnnotations {
    if (this.annotations.length === 0) {
      // No annotations, nothing to update
      return this;
    }
    const popped = this.annotations[this.annotations.length - 1];
    const remaining = this.annotations.slice(0, -1);
    const newRelations = this.relations
      .map((r) => r.updateForAnnotationDeletion(popped))
      .filter((r) => r !== undefined);

    return new PdfAnnotations(
      remaining,
      newRelations as RelationGroup[],
      this.docTypes,
      true
    );
  }
}
