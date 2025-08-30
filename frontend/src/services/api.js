import axios from "axios";

export const sendImageToOCR = async (file) => {
  const formData = new FormData();
  formData.append("file", file);

  const response = await axios.post("http://localhost:5000/ocr", formData);
  return response.data;
};
