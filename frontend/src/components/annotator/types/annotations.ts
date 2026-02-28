import { v4 as uuidv4 } from "uuid";
import { AnnotationLabelType } from "../../../types/graphql-api";
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
    public id: string | string = uuidv4(),
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
    const sourceEmpty = this.sourceIds.length === 0;
    const targetEmpty = this.targetIds.length === 0;

    const newSourceIds = this.sourceIds.filter((id) => id !== a.id);
    const newTargetIds = this.targetIds.filter((id) => id !== a.id);

    const nowSourceEmpty = this.sourceIds.length === 0;
    const nowTargetEmpty = this.targetIds.length === 0;

    // Only target had any annotations, now it has none,
    // so delete.
    if (sourceEmpty && nowTargetEmpty) {
      return undefined;
    }
    // Only source had any annotations, now it has none,
    // so delete.
    if (targetEmpty && nowSourceEmpty) {
      return undefined;
    }
    // Source was not empty, but now it is, so delete.
    if (!sourceEmpty && nowSourceEmpty) {
      return undefined;
    }
    // Target was not empty, but now it is, so delete.
    if (!targetEmpty && nowTargetEmpty) {
      return undefined;
    }

    return new RelationGroup(newSourceIds, newTargetIds, this.label);
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

  constructor(
    public readonly page: number,
    public readonly annotationLabel: AnnotationLabelType,
    public readonly rawText: string,
    public readonly structural: boolean,
    public readonly json: MultipageAnnotationJson,
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
    const popped = this.annotations.pop();
    if (!popped) {
      // No annotations, nothing to update
      return this;
    }
    const newRelations = this.relations
      .map((r) => r.updateForAnnotationDeletion(popped))
      .filter((r) => r !== undefined);

    return new PdfAnnotations(
      this.annotations,
      newRelations as RelationGroup[],
      this.docTypes,
      true
    );
  }
}
