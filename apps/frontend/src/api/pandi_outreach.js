"use strict";
/**
 * Pandi Outreach API Client (Session 35)
 * Client service invitation campaign management
 */
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
exports.fetchOutreachContacts = fetchOutreachContacts;
exports.createCampaign = createCampaign;
exports.previewCampaign = previewCampaign;
exports.sendCampaign = sendCampaign;
exports.fetchCampaign = fetchCampaign;
exports.fetchCampaigns = fetchCampaigns;
var API_BASE = import.meta.env.VITE_API_URL || '';
/**
 * List contacts available for outreach
 */
function fetchOutreachContacts(filters_1) {
    return __awaiter(this, arguments, void 0, function (filters, limit, offset) {
        var params, response;
        if (limit === void 0) { limit = 100; }
        if (offset === void 0) { offset = 0; }
        return __generator(this, function (_a) {
            switch (_a.label) {
                case 0:
                    params = new URLSearchParams();
                    if (filters === null || filters === void 0 ? void 0 : filters.organization_ids) {
                        filters.organization_ids.forEach(function (id) { return params.append('organization_ids', id); });
                    }
                    if (filters === null || filters === void 0 ? void 0 : filters.domains) {
                        filters.domains.forEach(function (d) { return params.append('domains', d); });
                    }
                    if (filters === null || filters === void 0 ? void 0 : filters.clearance_levels) {
                        filters.clearance_levels.forEach(function (c) { return params.append('clearance_levels', c); });
                    }
                    params.append('limit', String(limit));
                    params.append('offset', String(offset));
                    return [4 /*yield*/, fetch("".concat(API_BASE, "/admin/pandi/outreach/contacts?").concat(params), { credentials: 'include' })];
                case 1:
                    response = _a.sent();
                    if (!response.ok) {
                        throw new Error("Failed to fetch contacts: ".concat(response.statusText));
                    }
                    return [2 /*return*/, response.json()];
            }
        });
    });
}
/**
 * Create new outreach campaign
 */
function createCampaign(data) {
    return __awaiter(this, void 0, void 0, function () {
        var response;
        return __generator(this, function (_a) {
            switch (_a.label) {
                case 0: return [4 /*yield*/, fetch("".concat(API_BASE, "/admin/pandi/outreach/campaigns"), {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(data),
                        credentials: 'include'
                    })];
                case 1:
                    response = _a.sent();
                    if (!response.ok) {
                        throw new Error("Failed to create campaign: ".concat(response.statusText));
                    }
                    return [2 /*return*/, response.json()];
            }
        });
    });
}
/**
 * Get campaign preview with contacts and rendered messages
 */
function previewCampaign(campaignId_1) {
    return __awaiter(this, arguments, void 0, function (campaignId, limit, offset) {
        var params, response;
        if (limit === void 0) { limit = 10; }
        if (offset === void 0) { offset = 0; }
        return __generator(this, function (_a) {
            switch (_a.label) {
                case 0:
                    params = new URLSearchParams({
                        limit: String(limit),
                        offset: String(offset)
                    });
                    return [4 /*yield*/, fetch("".concat(API_BASE, "/admin/pandi/outreach/campaigns/").concat(campaignId, "/preview?").concat(params), { credentials: 'include' })];
                case 1:
                    response = _a.sent();
                    if (!response.ok) {
                        throw new Error("Failed to preview campaign: ".concat(response.statusText));
                    }
                    return [2 /*return*/, response.json()];
            }
        });
    });
}
/**
 * Send campaign
 */
function sendCampaign(campaignId) {
    return __awaiter(this, void 0, void 0, function () {
        var response;
        return __generator(this, function (_a) {
            switch (_a.label) {
                case 0: return [4 /*yield*/, fetch("".concat(API_BASE, "/admin/pandi/outreach/campaigns/").concat(campaignId, "/send"), {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ confirm: true }),
                        credentials: 'include'
                    })];
                case 1:
                    response = _a.sent();
                    if (!response.ok) {
                        throw new Error("Failed to send campaign: ".concat(response.statusText));
                    }
                    return [2 /*return*/, response.json()];
            }
        });
    });
}
/**
 * Get campaign details
 */
function fetchCampaign(campaignId) {
    return __awaiter(this, void 0, void 0, function () {
        var response;
        return __generator(this, function (_a) {
            switch (_a.label) {
                case 0: return [4 /*yield*/, fetch("".concat(API_BASE, "/admin/pandi/outreach/campaigns/").concat(campaignId), { credentials: 'include' })];
                case 1:
                    response = _a.sent();
                    if (!response.ok) {
                        throw new Error("Failed to fetch campaign: ".concat(response.statusText));
                    }
                    return [2 /*return*/, response.json()];
            }
        });
    });
}
/**
 * List campaigns
 */
function fetchCampaigns() {
    return __awaiter(this, arguments, void 0, function (limit, offset) {
        var params, response;
        if (limit === void 0) { limit = 20; }
        if (offset === void 0) { offset = 0; }
        return __generator(this, function (_a) {
            switch (_a.label) {
                case 0:
                    params = new URLSearchParams({
                        limit: String(limit),
                        offset: String(offset)
                    });
                    return [4 /*yield*/, fetch("".concat(API_BASE, "/admin/pandi/outreach/campaigns?").concat(params), { credentials: 'include' })];
                case 1:
                    response = _a.sent();
                    if (!response.ok) {
                        throw new Error("Failed to fetch campaigns: ".concat(response.statusText));
                    }
                    return [2 /*return*/, response.json()];
            }
        });
    });
}
