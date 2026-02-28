module.exports = {
    testMatch: ['**/tests/**/*.test.js'],
    setupFiles: ['tests/setup.js'],
    fileParallelism: false,
    maxWorkers: 1, // store/workflow 共用 data_test，單一 worker 避免 EPERM/ENOENT
};
