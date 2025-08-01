import { AuthProvider } from './Context/AuthContext.tsx';
import {BrowserRouter, Navigate, Route, Routes} from 'react-router-dom'
import PrivateRoute from "./Components/PrivateRoute/PrivateRoute.tsx";
import Login from "./Pages/Login/Login.tsx"
import Models from "./Pages/Models/Models.tsx";
import Register from "./Pages/Register/Register.tsx";
import Datasets from "./Pages/Datasets/Datasets.tsx";
import DatasetQuestions from "./Pages/DatasetQuestions/DatasetQuestions.tsx";
import Evaluations from "./Pages/Evaluations/Evaluations.tsx";
import TestDetails from "./Pages/TestDetails/TestDetails.tsx";
import CommunityDatasets from "./Pages/CommunityDatasets/CommunityDatasets.tsx";
import Logout from "./Pages/Logout.tsx";
import Results from "./Pages/Results/Results.tsx";

function App() {

  return (
      <BrowserRouter>
        <AuthProvider>
          <Routes>

              <Route path="/" element={<Navigate to="/login" />} />
              <Route path="/register" element={<Register />} />
              <Route path="/login" element={<Login />} />

              {/* Protected Routes */}
              <Route element={<PrivateRoute />}>
                    <Route path="/models" element={<Models />} />
                    <Route path="/datasets" element={<Datasets />} />
                    <Route path="/datasets/:datasetId/questions" element={<DatasetQuestions />}/>
                    <Route path="/evaluations" element={<Evaluations/>} />
                    <Route path="/evaluations/:testId/results" element={<TestDetails />} />
                    <Route path="/overview" element={<Results />} />
                    <Route path="/community" element={<CommunityDatasets/>} />
                    <Route path="/logout" element={<Logout />} />

              </Route>

          </Routes>
        </AuthProvider>
      </BrowserRouter>
  )
}

export default App
