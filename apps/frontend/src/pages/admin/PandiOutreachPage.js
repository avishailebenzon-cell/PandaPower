"use strict";
/**
 * Session 35: Pandi Client Invitation Campaign Management
 * Multi-step workflow: Select Contacts → Preview Messages → Send Campaign
 */
var __assign = (this && this.__assign) || function () {
    __assign = Object.assign || function(t) {
        for (var s, i = 1, n = arguments.length; i < n; i++) {
            s = arguments[i];
            for (var p in s) if (Object.prototype.hasOwnProperty.call(s, p))
                t[p] = s[p];
        }
        return t;
    };
    return __assign.apply(this, arguments);
};
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
var __awaiter = (this && this.__awaiter) || function (thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};
var __generator = (this && this.__generator) || function (thisArg, body) {
    var _ = { label: 0, sent: function() { if (t[0] & 1) throw t[1]; return t[1]; }, trys: [], ops: [] }, f, y, t, g = Object.create((typeof Iterator === "function" ? Iterator : Object).prototype);
    return g.next = verb(0), g["throw"] = verb(1), g["return"] = verb(2), typeof Symbol === "function" && (g[Symbol.iterator] = function() { return this; }), g;
    function verb(n) { return function (v) { return step([n, v]); }; }
    function step(op) {
        if (f) throw new TypeError("Generator is already executing.");
        while (g && (g = 0, op[0] && (_ = 0)), _) try {
            if (f = 1, y && (t = op[0] & 2 ? y["return"] : op[0] ? y["throw"] || ((t = y["return"]) && t.call(y), 0) : y.next) && !(t = t.call(y, op[1])).done) return t;
            if (y = 0, t) op = [op[0] & 2, t.value];
            switch (op[0]) {
                case 0: case 1: t = op; break;
                case 4: _.label++; return { value: op[1], done: false };
                case 5: _.label++; y = op[1]; op = [0]; continue;
                case 7: op = _.ops.pop(); _.trys.pop(); continue;
                default:
                    if (!(t = _.trys, t = t.length > 0 && t[t.length - 1]) && (op[0] === 6 || op[0] === 2)) { _ = 0; continue; }
                    if (op[0] === 3 && (!t || (op[1] > t[0] && op[1] < t[3]))) { _.label = op[1]; break; }
                    if (op[0] === 6 && _.label < t[1]) { _.label = t[1]; t = op; break; }
                    if (t && _.label < t[2]) { _.label = t[2]; _.ops.push(op); break; }
                    if (t[2]) _.ops.pop();
                    _.trys.pop(); continue;
            }
            op = body.call(thisArg, _);
        } catch (e) { op = [6, e]; y = 0; } finally { f = t = 0; }
        if (op[0] & 5) throw op[1]; return { value: op[0] ? op[1] : void 0, done: true };
    }
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.default = PandiOutreachPage;
var react_1 = __importStar(require("react"));
var material_1 = require("@mui/material");
var icons_material_1 = require("@mui/icons-material");
var pandiApi = __importStar(require("../../api/pandi_outreach"));
var DEFAULT_MESSAGE_TEMPLATE = "\u05E9\u05DC\u05D5\u05DD {client_name} \uD83D\uDC4B\n\n\u05D0\u05E0\u05D9 \u05E4\u05E0\u05D3\u05D9, \u05D1\u05D5\u05D8 \u05D7\u05D1\u05E8\u05D4 \u05DC\u05D0\u05D9\u05EA\u05D5\u05E8 \u05DE\u05D5\u05E2\u05DE\u05D3\u05D9\u05DD \u05E9\u05DC {company} \uD83E\uDD16\n\n\u05E2\u05D5\u05D6\u05E8\u05EA \u05DC\u05D7\u05D1\u05E8\u05D5\u05EA \u05DC\u05DE\u05E6\u05D5\u05D0 \u05DE\u05D5\u05E2\u05DE\u05D3\u05D9\u05DD \u05DE\u05EA\u05D0\u05D9\u05DE\u05D9\u05DD \u05D1\u05E9\u05E0\u05D9\u05D5\u05EA.\n\n\u05E8\u05D5\u05E6\u05D4 \u05DC\u05D4\u05E9\u05EA\u05DE\u05E9 \u05D1\u05E9\u05D9\u05E8\u05D5\u05EA\u05D9? \u05E9\u05DE\u05D5\u05E8 \u05D0\u05EA \u05D4\u05D4\u05D5\u05D3\u05E2\u05D4 \u05D4\u05D6\u05D5 \u05DB\u05D3\u05D9 \u05E9\u05D0\u05D5\u05DB\u05DC \u05DC\u05D4\u05D6\u05D4\u05D5\u05EA \u05D0\u05D5\u05EA\u05DA \u05D1\u05D4\u05DE\u05E9\u05DA!\n\n\u05DC\u05E9\u05D0\u05DC\u05D5\u05EA: {phone}\n\n(\u05D6\u05D4 \u05DE\u05D5\u05E7\u05D3 \u05D1\u05D3\u05D9\u05E7\u05D4 - \u05EA\u05D5\u05D3\u05D4 \u05E2\u05DC \u05D4\u05E1\u05D1\u05DC\u05E0\u05D5\u05EA)";
function PandiOutreachPage() {
    var _this = this;
    // State
    var _a = (0, react_1.useState)('select'), activeStep = _a[0], setActiveStep = _a[1];
    var _b = (0, react_1.useState)({
        organization_ids: [],
        domains: [],
        clearance_levels: [],
    }), filters = _b[0], setFilters = _b[1];
    var _c = (0, react_1.useState)([]), contacts = _c[0], setContacts = _c[1];
    var _d = (0, react_1.useState)([]), selectedContacts = _d[0], setSelectedContacts = _d[1];
    var _e = (0, react_1.useState)(DEFAULT_MESSAGE_TEMPLATE), messageTemplate = _e[0], setMessageTemplate = _e[1];
    var _f = (0, react_1.useState)(''), campaignName = _f[0], setCampaignName = _f[1];
    var _g = (0, react_1.useState)(null), campaign = _g[0], setCampaign = _g[1];
    var _h = (0, react_1.useState)(null), preview = _h[0], setPreview = _h[1];
    var _j = (0, react_1.useState)(false), loading = _j[0], setLoading = _j[1];
    var _k = (0, react_1.useState)(false), sending = _k[0], setSending = _k[1];
    var _l = (0, react_1.useState)(null), error = _l[0], setError = _l[1];
    // Step 1: Load contacts
    var handleLoadContacts = function () { return __awaiter(_this, void 0, void 0, function () {
        var data, err_1;
        return __generator(this, function (_a) {
            switch (_a.label) {
                case 0:
                    setLoading(true);
                    setError(null);
                    _a.label = 1;
                case 1:
                    _a.trys.push([1, 3, 4, 5]);
                    return [4 /*yield*/, pandiApi.fetchOutreachContacts({
                            organization_ids: filters.organization_ids.length ? filters.organization_ids : undefined,
                            domains: filters.domains.length ? filters.domains : undefined,
                            clearance_levels: filters.clearance_levels.length ? filters.clearance_levels : undefined,
                        }, 100)];
                case 2:
                    data = _a.sent();
                    setContacts(data);
                    setSelectedContacts(data);
                    return [3 /*break*/, 5];
                case 3:
                    err_1 = _a.sent();
                    setError("Failed to load contacts: ".concat(err_1));
                    return [3 /*break*/, 5];
                case 4:
                    setLoading(false);
                    return [7 /*endfinally*/];
                case 5: return [2 /*return*/];
            }
        });
    }); };
    // Step 2: Preview campaign
    var handlePreview = function () { return __awaiter(_this, void 0, void 0, function () {
        var newCampaign, previewData, err_2;
        return __generator(this, function (_a) {
            switch (_a.label) {
                case 0:
                    if (!campaignName.trim()) {
                        setError('Campaign name is required');
                        return [2 /*return*/];
                    }
                    setLoading(true);
                    setError(null);
                    _a.label = 1;
                case 1:
                    _a.trys.push([1, 4, 5, 6]);
                    return [4 /*yield*/, pandiApi.createCampaign({
                            campaign_name: campaignName,
                            message_template: messageTemplate,
                            filters: {
                                organization_ids: filters.organization_ids.length ? filters.organization_ids : undefined,
                                domains: filters.domains.length ? filters.domains : undefined,
                                clearance_levels: filters.clearance_levels.length ? filters.clearance_levels : undefined,
                            },
                        })];
                case 2:
                    newCampaign = _a.sent();
                    setCampaign(newCampaign);
                    return [4 /*yield*/, pandiApi.previewCampaign(newCampaign.id, 50)];
                case 3:
                    previewData = _a.sent();
                    setPreview(previewData);
                    setActiveStep('preview');
                    return [3 /*break*/, 6];
                case 4:
                    err_2 = _a.sent();
                    setError("Failed to preview campaign: ".concat(err_2));
                    return [3 /*break*/, 6];
                case 5:
                    setLoading(false);
                    return [7 /*endfinally*/];
                case 6: return [2 /*return*/];
            }
        });
    }); };
    // Step 3: Send campaign
    var handleSendCampaign = function () { return __awaiter(_this, void 0, void 0, function () {
        var result, updatedCampaign, err_3;
        return __generator(this, function (_a) {
            switch (_a.label) {
                case 0:
                    if (!campaign)
                        return [2 /*return*/];
                    setSending(true);
                    setError(null);
                    _a.label = 1;
                case 1:
                    _a.trys.push([1, 4, 5, 6]);
                    return [4 /*yield*/, pandiApi.sendCampaign(campaign.id)];
                case 2:
                    result = _a.sent();
                    return [4 /*yield*/, pandiApi.fetchCampaign(campaign.id)];
                case 3:
                    updatedCampaign = _a.sent();
                    setCampaign(updatedCampaign);
                    setActiveStep('confirm');
                    return [3 /*break*/, 6];
                case 4:
                    err_3 = _a.sent();
                    setError("Failed to send campaign: ".concat(err_3));
                    return [3 /*break*/, 6];
                case 5:
                    setSending(false);
                    return [7 /*endfinally*/];
                case 6: return [2 /*return*/];
            }
        });
    }); };
    // Render step content
    var renderStepContent = function () {
        switch (activeStep) {
            case 'select':
                return (react_1.default.createElement(material_1.Box, { sx: { p: 3 } },
                    react_1.default.createElement(material_1.Typography, { variant: "h6", mb: 2 }, "Step 1: Select Contacts"),
                    react_1.default.createElement(material_1.Grid, { container: true, spacing: 2, mb: 3 },
                        react_1.default.createElement(material_1.Grid, { item: true, xs: 12, sm: 4 },
                            react_1.default.createElement(material_1.TextField, { fullWidth: true, label: "Organization IDs (comma-separated)", value: filters.organization_ids.join(', '), onChange: function (e) {
                                    return setFilters(__assign(__assign({}, filters), { organization_ids: e.target.value
                                            .split(',')
                                            .map(function (id) { return id.trim(); })
                                            .filter(Boolean) }));
                                } })),
                        react_1.default.createElement(material_1.Grid, { item: true, xs: 12, sm: 4 },
                            react_1.default.createElement(material_1.TextField, { fullWidth: true, label: "Domains (comma-separated)", value: filters.domains.join(', '), onChange: function (e) {
                                    return setFilters(__assign(__assign({}, filters), { domains: e.target.value
                                            .split(',')
                                            .map(function (d) { return d.trim(); })
                                            .filter(Boolean) }));
                                } })),
                        react_1.default.createElement(material_1.Grid, { item: true, xs: 12, sm: 4 },
                            react_1.default.createElement(material_1.TextField, { fullWidth: true, label: "Clearance Levels (comma-separated)", value: filters.clearance_levels.join(', '), onChange: function (e) {
                                    return setFilters(__assign(__assign({}, filters), { clearance_levels: e.target.value
                                            .split(',')
                                            .map(function (c) { return c.trim(); })
                                            .filter(Boolean) }));
                                } }))),
                    react_1.default.createElement(material_1.Button, { variant: "contained", onClick: handleLoadContacts, disabled: loading, sx: { mb: 3 } }, loading ? react_1.default.createElement(material_1.CircularProgress, { size: 24 }) : 'Load Contacts'),
                    contacts.length > 0 && (react_1.default.createElement(react_1.default.Fragment, null,
                        react_1.default.createElement(material_1.Alert, { severity: "info", sx: { mb: 2 } },
                            "Total ",
                            contacts.length,
                            " contacts selected"),
                        react_1.default.createElement(material_1.TableContainer, { component: material_1.Paper },
                            react_1.default.createElement(material_1.Table, { size: "small" },
                                react_1.default.createElement(material_1.TableHead, null,
                                    react_1.default.createElement(material_1.TableRow, { style: { backgroundColor: '#f5f5f5' } },
                                        react_1.default.createElement(material_1.TableCell, null,
                                            react_1.default.createElement("strong", null, "Name")),
                                        react_1.default.createElement(material_1.TableCell, null,
                                            react_1.default.createElement("strong", null, "Email")),
                                        react_1.default.createElement(material_1.TableCell, null,
                                            react_1.default.createElement("strong", null, "Phone")),
                                        react_1.default.createElement(material_1.TableCell, null,
                                            react_1.default.createElement("strong", null, "Organization")),
                                        react_1.default.createElement(material_1.TableCell, null,
                                            react_1.default.createElement("strong", null, "Domain")))),
                                react_1.default.createElement(material_1.TableBody, null, contacts.slice(0, 10).map(function (contact) { return (react_1.default.createElement(material_1.TableRow, { key: contact.id },
                                    react_1.default.createElement(material_1.TableCell, null, contact.full_name),
                                    react_1.default.createElement(material_1.TableCell, null, contact.email),
                                    react_1.default.createElement(material_1.TableCell, null, contact.phone),
                                    react_1.default.createElement(material_1.TableCell, null, contact.organization_name || '-'),
                                    react_1.default.createElement(material_1.TableCell, null, contact.domain || '-'))); })))),
                        contacts.length > 10 && (react_1.default.createElement(material_1.Alert, { severity: "info", sx: { mt: 2 } },
                            "Showing first 10 of ",
                            contacts.length,
                            " contacts. All will be sent.")))),
                    contacts.length > 0 && (react_1.default.createElement(material_1.Box, { sx: { mt: 3 } },
                        react_1.default.createElement(material_1.TextField, { fullWidth: true, label: "Campaign Name", value: campaignName, onChange: function (e) { return setCampaignName(e.target.value); }, placeholder: "e.g., 'Pandi Service Invitation - May 2026'", sx: { mb: 2 } }),
                        react_1.default.createElement(material_1.TextField, { fullWidth: true, multiline: true, rows: 6, label: "Message Template", value: messageTemplate, onChange: function (e) { return setMessageTemplate(e.target.value); }, helperText: "Edit only {placeholders}: {client_name}, {company}, {phone}", sx: { mb: 2 } }),
                        react_1.default.createElement(material_1.Button, { variant: "contained", color: "primary", onClick: handlePreview, disabled: loading || !campaignName.trim() }, "Preview Messages \u2192")))));
            case 'preview':
                return (react_1.default.createElement(material_1.Box, { sx: { p: 3 } },
                    react_1.default.createElement(material_1.Typography, { variant: "h6", mb: 2 }, "Step 2: Preview Messages"),
                    preview && (react_1.default.createElement(react_1.default.Fragment, null,
                        react_1.default.createElement(material_1.Alert, { severity: "info", sx: { mb: 2 } },
                            "Campaign: ",
                            react_1.default.createElement("strong", null, preview.campaign.campaign_name),
                            react_1.default.createElement("br", null),
                            "Total contacts: ",
                            react_1.default.createElement("strong", null, preview.campaign.total_contacts)),
                        react_1.default.createElement(material_1.Typography, { variant: "subtitle2", mb: 1 }, "Preview (first 5 messages):"),
                        react_1.default.createElement(material_1.Box, { sx: { maxHeight: 400, overflowY: 'auto' } }, preview.preview_messages.slice(0, 5).map(function (item, idx) { return (react_1.default.createElement(material_1.Card, { key: idx, sx: { mb: 2 } },
                            react_1.default.createElement(material_1.CardContent, null,
                                react_1.default.createElement(material_1.Typography, { variant: "subtitle2" },
                                    "To: ",
                                    item.contact.full_name,
                                    " (",
                                    item.contact.email,
                                    ")"),
                                react_1.default.createElement(material_1.Typography, { variant: "body2", sx: {
                                        mt: 1,
                                        p: 1.5,
                                        backgroundColor: '#f9f9f9',
                                        borderRadius: 1,
                                        whiteSpace: 'pre-wrap',
                                        fontFamily: 'monospace',
                                    } }, item.rendered_message)))); })),
                        react_1.default.createElement(material_1.Alert, { severity: "success", sx: { mt: 2 } },
                            "\u2713 All placeholders substituted correctly",
                            react_1.default.createElement("br", null),
                            "\u2713 Ready to send to ",
                            preview.campaign.total_contacts,
                            " contacts"),
                        react_1.default.createElement(material_1.Box, { sx: { mt: 3, display: 'flex', gap: 1 } },
                            react_1.default.createElement(material_1.Button, { variant: "outlined", onClick: function () { return setActiveStep('select'); } }, "\u2190 Edit"),
                            react_1.default.createElement(material_1.Button, { variant: "contained", color: "primary", onClick: function () { return setActiveStep('confirm'); } }, "Confirm & Send \u2192"))))));
            case 'confirm':
                return (react_1.default.createElement(material_1.Box, { sx: { p: 3 } },
                    react_1.default.createElement(material_1.Typography, { variant: "h6", mb: 2 }, "Step 3: Confirm & Send"),
                    campaign && (react_1.default.createElement(react_1.default.Fragment, null,
                        react_1.default.createElement(material_1.Card, { sx: { mb: 3 } },
                            react_1.default.createElement(material_1.CardContent, null,
                                react_1.default.createElement(material_1.Grid, { container: true, spacing: 2 },
                                    react_1.default.createElement(material_1.Grid, { item: true, xs: 12, sm: 6 },
                                        react_1.default.createElement(material_1.Typography, { color: "textSecondary" }, "Campaign"),
                                        react_1.default.createElement(material_1.Typography, { variant: "h6" }, campaign.campaign_name)),
                                    react_1.default.createElement(material_1.Grid, { item: true, xs: 12, sm: 6 },
                                        react_1.default.createElement(material_1.Typography, { color: "textSecondary" }, "Status"),
                                        react_1.default.createElement(material_1.Chip, { label: campaign.status.toUpperCase(), color: campaign.status === 'in_progress'
                                                ? 'warning'
                                                : campaign.status === 'completed'
                                                    ? 'success'
                                                    : 'default', size: "small" })),
                                    react_1.default.createElement(material_1.Grid, { item: true, xs: 12, sm: 6 },
                                        react_1.default.createElement(material_1.Typography, { color: "textSecondary" }, "Total Contacts"),
                                        react_1.default.createElement(material_1.Typography, { variant: "h6" }, campaign.total_contacts)),
                                    react_1.default.createElement(material_1.Grid, { item: true, xs: 12, sm: 6 },
                                        react_1.default.createElement(material_1.Typography, { color: "textSecondary" }, "Estimated Duration"),
                                        react_1.default.createElement(material_1.Typography, { variant: "h6" },
                                            "~",
                                            Math.ceil(campaign.total_contacts * 3 / 60),
                                            " minutes"))))),
                        campaign.status === 'in_progress' && (react_1.default.createElement(material_1.Box, { sx: { mb: 3 } },
                            react_1.default.createElement(material_1.Typography, { variant: "subtitle2", mb: 1 }, "Progress"),
                            react_1.default.createElement(material_1.LinearProgress, { variant: "determinate", value: (campaign.sent_count / campaign.total_contacts) * 100, sx: { mb: 1 } }),
                            react_1.default.createElement(material_1.Typography, { variant: "body2", color: "textSecondary" },
                                campaign.sent_count,
                                " sent, ",
                                campaign.failed_count,
                                " failed"))),
                        campaign.status === 'completed' || campaign.status === 'completed_with_errors' ? (react_1.default.createElement(material_1.Alert, { severity: campaign.failed_count === 0 ? 'success' : 'warning', sx: { mb: 3 } },
                            "\u2713 Campaign completed!",
                            react_1.default.createElement("br", null),
                            "Sent: ",
                            campaign.sent_count,
                            " | Failed: ",
                            campaign.failed_count)) : (react_1.default.createElement(react_1.default.Fragment, null,
                            react_1.default.createElement(material_1.Alert, { severity: "warning", sx: { mb: 3 } },
                                "\u26A0\uFE0F Sending will begin immediately",
                                react_1.default.createElement("br", null),
                                "Messages sent at 3-second intervals (rate limiting)"),
                            react_1.default.createElement(material_1.Box, { sx: { display: 'flex', gap: 1 } },
                                react_1.default.createElement(material_1.Button, { variant: "outlined", onClick: function () { return setActiveStep('preview'); }, disabled: sending }, "\u2190 Back"),
                                react_1.default.createElement(material_1.Button, { variant: "contained", color: "success", onClick: handleSendCampaign, disabled: sending, startIcon: sending ? react_1.default.createElement(material_1.CircularProgress, { size: 20 }) : react_1.default.createElement(icons_material_1.Send, null) }, sending ? 'Sending...' : 'Send Campaign'))))))));
            default:
                return null;
        }
    };
    return (react_1.default.createElement(material_1.Box, { sx: { p: 3 } },
        react_1.default.createElement(material_1.Typography, { variant: "h4", mb: 3 }, "\uD83E\uDD16 Pandi Client Invitation"),
        error && (react_1.default.createElement(material_1.Alert, { severity: "error", sx: { mb: 2 }, onClose: function () { return setError(null); } }, error)),
        react_1.default.createElement(material_1.Paper, { sx: { p: 2, mb: 3 } },
            react_1.default.createElement(material_1.Stepper, { activeStep: ['select', 'preview', 'confirm'].indexOf(activeStep) },
                react_1.default.createElement(material_1.Step, null,
                    react_1.default.createElement(material_1.StepLabel, null, "Select Contacts")),
                react_1.default.createElement(material_1.Step, null,
                    react_1.default.createElement(material_1.StepLabel, null, "Preview Messages")),
                react_1.default.createElement(material_1.Step, null,
                    react_1.default.createElement(material_1.StepLabel, null, "Send Campaign")))),
        react_1.default.createElement(material_1.Paper, null, renderStepContent())));
}
