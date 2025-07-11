import React, { useEffect, useState } from "react";
import TestService from "../../Services/TestService";
import './Evaluations.css';
import '../../Components/CreateTestModal/CreateTestModal.css'; // For modal styles if any are shared
import { Test } from "../../types/Test";
import { useNavigate } from "react-router-dom";
import SearchIcon from "../../assets/searchIcon.svg?react";
import { Dataset } from "../../types/Dataset.ts"; // For modal
import { LLMModel } from "../../types/LLMModel.ts"; // For modal
import DatasetService from "../../Services/DatasetService.ts"; // For modal
import LLMModelService, { TestedModels } from "../../Services/LLMModelService.ts"; // For modal and filters
import CreateTestModal from "../../Components/CreateTestModal/CreateTestModal.tsx";
import Select, { StylesConfig, GroupBase, SingleValue } from 'react-select';
import ResultsService, {SelectableDataset} from "../../Services/ResultsService.ts"; // Import SingleValue for onChange type


const Evaluations: React.FC = () => {
    const [tests, setTests] = useState<Test[]>([]); // This will hold the tests from backend (already filtered/sorted)
    const [showCreateModal, setShowCreateModal] = useState<boolean>(false);

    // --- States for CreateTestModal (passed as props) ---
    const [modalDatasets, setModalDatasets] = useState<Dataset[]>([]);
    const [modalModels, setModalModels] = useState<LLMModel[]>([]);
    const [selectedDatasetForCreation, setSelectedDatasetForCreation] = useState<string>(''); // ID
    const [selectedModelForCreation, setSelectedModelForCreation] = useState<string>(''); // ID
    // ---------------------------------------------------

    const [filterDatasetName, setFilterDatasetName] = useState<string>('');
    const [filterModelName, setFilterModelName] = useState<string>('');
    const [sortCriteria, setSortCriteria] = useState<string>('id_desc'); // Default sort: accuracy_percentage_desc

    // --- States to populate filter dropdowns ---
    const [availableFilterDatasets, setAvailableFilterDatasets] = useState<SelectableDataset[]>([]);
    const [availableFilterModels, setAvailableFilterModels] = useState<TestedModels[]>([]); // Using TestedModels type
    // -----------------------------------------

    const [isLoading, setIsLoading] = useState<boolean>(true);
    const [isLoadingAction, setIsLoadingAction] = useState<boolean>(false); // For delete/create
    const navigate = useNavigate();

    // Fetch tests based on current filters and sort criteria from backend
    const fetchTests = async () => {
        setIsLoading(true);
        try {
            const data = await TestService.getAllTests(
                filterDatasetName,
                filterModelName,
                sortCriteria
            );
            setTests(data || []);
        } catch (error) {
            console.error("Error fetching tests:", error);
            setTests([]);
        } finally {
            setIsLoading(false);
        }
    };

    // Fetch data for create modal dropdowns (datasets & all models)
    const fetchModalData = async () => {
        setIsLoadingAction(true); // Or a specific modal loading state
        try {
            const [fetchedDatasets, fetchedModels] = await Promise.all([
                DatasetService.getAllDatasets(),
                LLMModelService.getAllLLMModels()
            ]);
            setModalDatasets(fetchedDatasets || []);
            setModalModels(fetchedModels || []);
        } catch (error) {
            console.error("Error fetching modal data:", error);
        } finally {
            setIsLoadingAction(false);
        }
    };

    // Fetch data for filter dropdowns (only tested datasets/models)
    const fetchFilterOptions = async () => {
        try {
            const [testedDs, testedMls] = await Promise.all([
                ResultsService.getAvailableDatasetsForModels([]), // New service method needed
                LLMModelService.getTestedModels()    // You have this
            ]);
            setAvailableFilterDatasets(testedDs || []);
            setAvailableFilterModels(testedMls || []);
        } catch (error) {
            console.error("Error fetching filter options:", error);
        }
    };


    useEffect(() => {
        fetchFilterOptions();
    }, []);

    useEffect(() => {
        fetchTests();
    }, [filterDatasetName, filterModelName, sortCriteria]);

    useEffect(() => {
        if (showCreateModal) {
            fetchModalData();
        }
    }, [showCreateModal]);


    const handleTestDetailsClick = (testId: string | number) => {
        navigate(`/evaluations/${testId}/results`);
    };

    const modalClose = () => {
        setShowCreateModal(false);
        setSelectedModelForCreation('');
        setSelectedDatasetForCreation('');
    }

    const handleDeleteClick = async (testId: string | number) => {
        const confirmed = window.confirm(`Are you sure you want to delete this test?`);
        if (confirmed) {
            try {
                setIsLoadingAction(true);
                const success = await TestService.deleteTestById(testId.toString());
                if (success) {
                    await fetchTests();
                } else {
                    alert("Failed to delete test. Please try again.");
                }
            } catch (error) {
                console.error("Error deleting test:", error);
                alert("An error occurred while deleting the test.");
            } finally {
                setIsLoadingAction(false);
            }
        }
    };

    const handleCreateTest = async () => {
        if (!selectedDatasetForCreation || !selectedModelForCreation) {
            alert("Please select both a dataset and a model for the new test.");
            return;
        }
        setIsLoadingAction(true);
        const newTest = await TestService.createTest(selectedDatasetForCreation, selectedModelForCreation);
        if (newTest) {
            setShowCreateModal(false);
            setSelectedDatasetForCreation("");
            setSelectedModelForCreation("");
            fetchTests();
            fetchFilterOptions();
        } else {
            console.error("Failed to create test");
            alert("Failed to create test. Please try again.");
        }
        setIsLoadingAction(false);
    };

    // Options for the consolidated sort dropdown
    const sortOptions: SelectOptionType[] = [
        { value: 'accuracy_desc', label: 'Best Accuracy' },
        { value: 'accuracy_asc', label: 'Worst Accuracy' },
        { value: 'time_desc', label: 'Best Time' },
        { value: 'time_asc', label: 'Worst Time' },
        { value: 'id_desc', label: 'Recent '},
        { value: 'id_asc', label: 'Oldest'}
    ];


    return (
        <div className="page evaluations-page">
            <div className="evaluations-header">
                <h1 className="page-title">Evaluations</h1>
                <button className="create-button" onClick={() => setShowCreateModal(true)} disabled={isLoadingAction}>
                    Create new test
                </button>
            </div>

            <div className="evaluations-controls">
                <div className="control-group">
                    <label htmlFor="filter-dataset-eval">Dataset:</label>
                    <Select<SelectOptionType, false, GroupBase<SelectOptionType>>
                        id="filter-dataset-eval"
                        styles={customSelectStyles}
                        options={[{ value: '', label: 'All Datasets' }, ...availableFilterDatasets.map(ds => ({ value: ds.name, label: ds.name }))]}
                        value={filterDatasetName ? { value: filterDatasetName, label: filterDatasetName } : { value: '', label: 'All Datasets' }}
                        onChange={(option: SingleValue<SelectOptionType>) => setFilterDatasetName(option ? option.value : '')}
                        placeholder="Filter by Dataset..."
                        isClearable
                        isSearchable
                    />
                </div>
                <div className="control-group">
                    <label htmlFor="filter-model-eval">Model:</label>
                    <Select<SelectOptionType, false, GroupBase<SelectOptionType>>
                        id="filter-model-eval"
                        styles={customSelectStyles}
                        options={[{ value: '', label: 'All Models' }, ...availableFilterModels.map(model => ({ value: model.name, label: model.name }))]}
                        value={filterModelName ? { value: filterModelName, label: filterModelName } : { value: '', label: 'All Models' }}
                        onChange={(option: SingleValue<SelectOptionType>) => setFilterModelName(option ? option.value : '')}
                        placeholder="Filter by Model..."
                        isClearable
                        isSearchable
                    />
                </div>
                <div className="control-group">
                    <label htmlFor="sort-criteria-eval">Sort by:</label>
                    <Select<SelectOptionType, false, GroupBase<SelectOptionType>>
                        id="sort-criteria-eval"
                        styles={customSelectStyles}
                        options={sortOptions}
                        value={sortOptions.find(opt => opt.value === sortCriteria)}
                        onChange={(option: SingleValue<SelectOptionType>) => setSortCriteria(option ? option.value : 'id_desc')}
                        defaultValue={sortOptions.find(opt => opt.value === 'id_desc')}
                    />
                </div>
            </div>

            <div className="tests-list-container">
                {isLoading && tests.length === 0 ? (
                    <p className="loading-text">Loading Tests...</p>
                ) : !isLoading && tests.length === 0 ? (
                    <p className="no-tests-text">
                        {filterDatasetName || filterModelName ? "No tests match your current filters." : "No Tests available."}
                    </p>
                ) : (
                    <div className="tests-list">
                        <div className="test-card header-row">
                            <span className="test-id header">ID</span>
                            <span className="test-dataset header">Dataset</span>
                            <span className="test-llm-model header">LLM Model</span>
                            <span className="test-correct-answers header">Correct Ans.</span>
                            <span className="test-accuracy header">Accuracy</span>
                            <span className="test-time header">Execution Time</span>
                            <span className="test-actions header">Actions</span>
                        </div>
                        {tests.map((test) => (
                            <div key={test.id} className="test-card data-row">
                                <span className="test-id">{test.id}</span>
                                <span className="test-dataset" title={test.dataset.name}>
                                    {test.dataset.name}
                                </span>
                                <span className="test-llm-model" title={test.llm_model.name || 'N/A'}>
                                    {test.llm_model.name}
                                </span>
                                <span className="test-correct-answers">
                                    {test.correct_answers}
                                </span>
                                <span className="test-accuracy">
                                    {test.accuracy_percentage !== null ? test.accuracy_percentage.toFixed(2) + '%' : 'N/A'}
                                </span>
                                <span className="test-time">
                                    {test.completed_at && test.started_at
                                        ? Math.round((new Date(test.completed_at).getTime() - new Date(test.started_at).getTime()) / 1000) + 's'
                                        : 'N/A'}
                                </span>
                                <div className="button-container test-actions">
                                    <button className="details-button" onClick={() => handleTestDetailsClick(test.id)}>
                                        <SearchIcon className="details-icon" />
                                        Details
                                    </button>
                                    <button className="delete-button" onClick={() => handleDeleteClick(test.id)} disabled={isLoadingAction}>
                                        Delete
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {showCreateModal && (
                <CreateTestModal
                    datasets={modalDatasets}
                    models={modalModels}
                    selectedDataset={selectedDatasetForCreation}
                    setSelectedDataset={setSelectedDatasetForCreation}
                    selectedModel={selectedModelForCreation}
                    setSelectedModel={setSelectedModelForCreation}
                    onCancel={modalClose}
                    onCreate={handleCreateTest}
                    isLoading={isLoadingAction}
                />
            )}
        </div>
    );
};

export default Evaluations;

// Define option type for react-select
interface SelectOptionType {
    value: string;
    label: string;
}


// --- react-select custom styles (can be moved to a separate file) ---
const customSelectStyles: StylesConfig<SelectOptionType, false, GroupBase<SelectOptionType>> = {
    control: (provided, state) => ({
        ...provided,
        backgroundColor: '#1e2235', // Darker input background
        borderColor: state.isFocused ? '#6a6fbf' : '#363c58',
        boxShadow: state.isFocused ? '0 0 0 1px #6a6fbf' : 'none',
        borderRadius: '8px',
        minHeight: '40px', // Consistent height with other inputs
        color: '#e0e4ff',
        fontSize: '0.9rem',
        minWidth: '200px', // Fixed width for filter/sort dropdowns
        width: '200px',
        '&:hover': { borderColor: '#6a6fbf' },
    }),
    menu: (provided) => ({
        ...provided,
        backgroundColor: '#2f354c', // Dropdown menu background
        borderRadius: '8px',
        marginTop: '4px',
        zIndex: 10, // Ensure dropdown is above other elements
    }),
    option: (provided, state) => ({
        ...provided,
        backgroundColor: state.isSelected ? '#6a6fbf' : state.isFocused ? '#3b4262' : '#2f354c',
        color: state.isSelected ? 'white' : '#e0e4ff',
        padding: '10px 12px',
        cursor: 'pointer',
        fontSize: '0.9rem',
        '&:active': { backgroundColor: '#5564ae' },
    }),
    singleValue: (provided) => ({ ...provided, color: '#e0e4ff' }),
    placeholder: (provided) => ({ ...provided, color: '#a0a7d3' }),
    input: (provided) => ({ ...provided, color: '#e0e4ff' }),
    dropdownIndicator: (provided) => ({ ...provided, color: '#a0a7d3', '&:hover': { color: '#e0e4ff' }}),
    clearIndicator: (provided) => ({ ...provided, color: '#a0a7d3', '&:hover': { color: '#e0e4ff' }}),
    menuList: (provided) => ({
        ...provided,
        '&::-webkit-scrollbar': { width: '8px' },
        '&::-webkit-scrollbar-track': { background: '#2a2f45', borderRadius: '10px' },
        '&::-webkit-scrollbar-thumb': { backgroundColor: '#4a5175', borderRadius: '10px', border: '2px solid #2a2f45' },
        '&::-webkit-scrollbar-thumb:hover': { backgroundColor: '#5a67d8' },
        scrollbarWidth: 'thin',
        scrollbarColor: '#4a5175 #2a2f45',
    }),
};