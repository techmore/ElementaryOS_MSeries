/* Original MSeries read-only IMCore adapter. Run with macOS osascript -l JavaScript.
 * Makes no Apple Events calls, signing overrides or SIP changes.
 * Private interfaces are probed at runtime; unavailable is never an empty list.
 */
ObjC.import('Foundation');

function fail(reason) { throw new Error(reason); }
function selector(name) { return $.NSSelectorFromString(name); }
function signature(object, name) {
    if (!object || !object.respondsToSelector(selector(name))) return null;
    var sig = object.methodSignatureForSelector(selector(name));
    if (!sig || Number(sig.numberOfArguments) !== 2) return null;
    return ObjC.unwrap($.NSString.stringWithUTF8String(sig.methodReturnType));
}
function objectValue(object, name, required) {
    var type = signature(object, name);
    if (!type || type[0] !== '@') {
        if (required) fail('Unsupported object accessor: ' + name);
        return null;
    }
    return object.performSelector(selector(name));
}
function plain(value) {
    return value ? ObjC.deepUnwrap(value) : null;
}
function readController(controller) {
    var fetchType = signature(controller, 'fetchPinnedConversationIdentifiersFromLocalStore');
    if (fetchType === 'v') {
        // This selector returns void in known headers. Never interpret its
        // return register as an object, as some public examples do.
        controller.fetchPinnedConversationIdentifiersFromLocalStore;
    } else if (fetchType && fetchType[0] !== '@') {
        fail('Unsupported pin-store refresh signature');
    }
    var config = plain(objectValue(controller, '_locallyStoredPinConfiguration', false));
    var identifiers = config && Array.isArray(config.pP) ? config.pP : null;
    if (identifiers === null) {
        var array = objectValue(controller, 'pinnedConversationIdentifiers', false);
        if (array) identifiers = plain(array);
        if (!Array.isArray(identifiers)) {
            var ordered = objectValue(controller, 'pinnedConversationIdentifierSet', false);
            identifiers = ordered ? plain(objectValue(ordered, 'array', false)) : null;
        }
        // A default empty collection before initialization does not prove that
        // the owner's signed-in Messages pin store was read successfully.
        if (!identifiers || !controller.hasCompletedInitialization)
            fail('Messages has not supplied an initialized pin configuration. Open Messages and let it sync, then retry.');
    }
    var metadata = plain(objectValue(controller, 'chatMetadata', false)) || {};
    return makeSnapshot(identifiers, metadata);
}
function makeSnapshot(identifiers, metadata) {
    if (!Array.isArray(identifiers) || identifiers.length > 32) fail('Unexpected pin list');
    var seen = Object.create(null);
    var pins = identifiers.map(function(identifier) {
        if (typeof identifier !== 'string' || !identifier.length || identifier.length > 2048 || /[\x00-\x1f\x7f]/.test(identifier) || seen[identifier])
            fail('Invalid or duplicate pin identifier');
        seen[identifier] = true;
        return {apple_identifier: identifier};
    });
    // Keep opaque group identity metadata for future qualified adapters. Never
    // read messages, chat.db, Apple Account credentials, or an entire KVS store.
    if (!metadata || typeof metadata !== 'object' || Array.isArray(metadata)) metadata = {};
    if (JSON.stringify(metadata).length > 65536) fail('Unexpected pin metadata size');
    return {schema: 'io.elementary.mseries.apple-message-pins', version: 1,
            source: 'macos-imcore', captured_at: new Date().toISOString(),
            source_os: ObjC.unwrap($.NSProcessInfo.processInfo.operatingSystemVersionString),
            pins: pins, metadata: metadata};
}
function selfTest() {
    ObjC.registerSubclass({name: 'MSeriesPinReaderFixture', methods: {
        fetchPinnedConversationIdentifiersFromLocalStore: {types: ['void', []], implementation: function() {}},
        _locallyStoredPinConfiguration: {types: ['id', []], implementation: function() {return $({pP: ['+15550100123', 'group-fixture']});}},
        chatMetadata: {types: ['id', []], implementation: function() {return $({});}}
    }});
    var fixture = $.MSeriesPinReaderFixture.alloc.init;
    if (signature(fixture, 'fetchPinnedConversationIdentifiersFromLocalStore') !== 'v') fail('Void ABI test failed');
    var snapshot = readController(fixture);
    if (snapshot.pins.length !== 2 || snapshot.pins[0].apple_identifier !== '+15550100123') fail('Ordered read test failed');
    if (makeSnapshot([], {}).pins.length !== 0) fail('Verified empty test failed');
    var rejected = false;
    try {makeSnapshot(['same', 'same'], {});} catch (_) {rejected = true;}
    if (!rejected) fail('Duplicate rejection failed');
    ObjC.registerSubclass({name: 'MSeriesUninitializedPinFixture', methods: {
        pinnedConversationIdentifiers: {types: ['id', []], implementation: function() {return $([]);}},
        hasCompletedInitialization: {types: ['bool', []], implementation: function() {return false;}}
    }});
    rejected = false;
    try {readController($.MSeriesUninitializedPinFixture.alloc.init);} catch (_) {rejected = true;}
    if (!rejected) fail('Uninitialized empty configuration was accepted');
    return 'Pin reader fixture tests passed; no Apple account accessed.';
}
function run(args) {
    if (args.length === 1 && args[0] === '--self-test') return selfTest();
    var probe = args.length === 1 && args[0] === '--probe';
    if (!probe && (args.length !== 2 || args[0] !== '--output'))
        fail('Usage: Export-Message-Pins.js --output /absolute/private/file.json | --probe');
    var diagnostics = {};
    try {
        var bundle = $.NSBundle.bundleWithPath('/System/Library/PrivateFrameworks/IMCore.framework');
        if (!bundle || !bundle.load) fail('IMCore could not be loaded');
        var cls = $.NSClassFromString('IMPinnedConversationsController');
        if (!cls) fail('Messages pin controller is unavailable on this macOS version');
        var controller = objectValue(cls, 'sharedInstance', true);
        if (!controller) fail('Messages did not provide a pin controller');
        diagnostics.fetch_return_type = signature(controller, 'fetchPinnedConversationIdentifiersFromLocalStore');
        diagnostics.local_configuration_return_type = signature(controller, '_locallyStoredPinConfiguration');
        if (signature(cls, 'processSupportsPinnedConversations'))
            diagnostics.process_supported = Boolean(cls.processSupportsPinnedConversations);
        var snapshot = readController(controller);
        if (probe) return JSON.stringify({status: 'ready', count: snapshot.pins.length, content_printed: false});
        var path = args[1];
        if (path[0] !== '/') fail('Choose an absolute output path');
        var error = Ref();
        var text = $(JSON.stringify(snapshot, null, 2) + '\n');
        if (!text.writeToFileAtomicallyEncodingError(path, true, $.NSUTF8StringEncoding, error))
            fail('Could not save the private export');
        if (!$.NSFileManager.defaultManager.setAttributesOfItemAtPathError($({NSFilePosixPermissions: 384}), path, error))
            fail('Could not secure the private export permissions');
        return 'Exported ' + snapshot.pins.length + ' ordered Messages pins. This is a snapshot; no phone settings changed.';
    } catch (error) {
        if (diagnostics.process_supported === false)
            error = new Error('No readable pin configuration. IMCore reports this helper process as unsupported; account initialization and permissions are not established. A successful export has not been verified.');
        if (probe) return JSON.stringify({status: 'unavailable', reason: String(error.message || error), diagnostics: diagnostics, content_printed: false});
        throw error;
    }
}
