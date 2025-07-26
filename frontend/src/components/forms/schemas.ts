//########################### NEW DOCUMENT FORM #################################

export const newDocForm_Schema = {
  title: "Document Details",
  type: "object",
  properties: {
    title: {
      type: "string",
      title: "Title:",
    },
    description: {
      type: "string",
      title: "Description:",
    },
  },
  required: ["title", "description"],
};

export const newDocForm_Ui_Schema = {
  description: {
    "ui:widget": "textarea",
    "ui:placeholder": "Add a description...",
  },
};

//########################### EDIT DOCUMENT FORM #################################

export const editDocForm_Schema = {
  title: "Document Details",
  type: "object",
  properties: {
    title: {
      type: "string",
      title: "Title:",
    },
    description: {
      type: "string",
      title: "Description:",
    },
  },
  required: ["title", "description"],
};

export const editDocForm_Ui_Schema = {
  description: {
    "ui:widget": "textarea",
    "ui:placeholder": "Add a description...",
  },
};

//########################### NEW CORPUS FORM ####################################

export const newCorpusForm_Schema = {
  title: "Corpus Details",
  type: "object",
  properties: {
    title: {
      type: "string",
      title: "Title:",
    },
    description: {
      type: "string",
      title: "Description:",
    },
  },
  required: ["title", "description"],
};

export const newCorpusForm_Ui_Schema = {
  description: {
    "ui:widget": "textarea",
    "ui:placeholder": "Add a description...",
  },
};

//########################### EDIT COLUMN FORM ####################################

export const editColumnForm_Schema = {
  title: "Column Details",
  type: "object",
  properties: {
    name: {
      type: "string",
      title: "Title:",
    },
    query: {
      type: "string",
      title: "What question shall we ask the LLM?",
    },
    matchText: {
      type: "string",
      title: "Provide a sample of the text you want to to find.",
    },
    outputType: {
      type: "string",
      title:
        "Please define the output data schema as Python primitive or Pydantic model.",
    },
    limitToLabel: {
      type: "string",
      title:
        "For now if you want to limit searching to annotations with certain label, provide label name.",
    },
    instructions: {
      type: "string",
      title:
        "If you want to provide detailed instructions to data parser, provide them here.",
    },
  },
  required: ["name", "outputType"],
};

export const editColumnForm_Ui_Schema = {
  matchText: {
    "ui:widget": "textarea",
    "ui:placeholder": "Add a description...",
  },
  outputType: {
    "ui:widget": "textarea",
    "ui:placeholder": "Add a description...",
  },
  instructions: {
    "ui:widget": "textarea",
    "ui:placeholder": "Add a description...",
  },
};

//########################### EDIT CORPUS FORM ####################################

export const editCorpusForm_Schema = {
  title: "Corpus Details",
  type: "object",
  properties: {
    title: {
      type: "string",
      title: "Title:",
    },
    description: {
      type: "string",
      title: "Description:",
    },
  },
  required: ["title", "description"],
};

export const editCorpusForm_Ui_Schema = {
  description: {
    "ui:widget": "textarea",
    "ui:placeholder": "Add a description...",
  },
};

//########################### NEW LABEL SET FORM ################################

export const newLabelSetForm_Schema = {
  title: "Label Set Details",
  type: "object",
  properties: {
    title: {
      type: "string",
      title: "Title:",
    },
    description: {
      type: "string",
      title: "Description:",
    },
  },
  required: ["title", "description"],
};

export const newLabelSetForm_Ui_Schema = {
  description: {
    "ui:widget": "textarea",
    "ui:placeholder": "Add a description...",
  },
};
