/*
 * Android 15(Conscrypt Mainline) TrustManagerImpl SSL pinning/CA bypass.
 * 시스템 CA 저장소에 mitmproxy CA를 심어도(bind-mount 등) 무시되는 문제를
 * TrustManagerImpl.verifyChain / checkTrustedRecursive를 후킹해 우회한다.
 * 자세한 배경은 docs/api_notes.md "HTTPS 인터셉트 방법" 참고.
 *
 * 사용법: frida -H 127.0.0.1:27042 -f com.vlocally.mealc.android -l docs/frida_ssl_bypass.js --no-pause
 */

Java.perform(function () {
  var TrustManagerImpl = Java.use('com.android.org.conscrypt.TrustManagerImpl');

  ['verifyChain'].forEach(function (methodName) {
    if (!TrustManagerImpl[methodName]) return;
    TrustManagerImpl[methodName].overloads.forEach(function (overload) {
      overload.implementation = function () {
        var chainArg = arguments[0];
        console.log('[bypass] TrustManagerImpl.' + methodName + '() called, host=' + arguments[2]);
        return chainArg;
      };
    });
  });

  ['checkTrustedRecursive'].forEach(function (methodName) {
    if (!TrustManagerImpl[methodName]) return;
    TrustManagerImpl[methodName].overloads.forEach(function (overload) {
      overload.implementation = function () {
        console.log('[bypass] TrustManagerImpl.' + methodName + '() called');
        return Java.use('java.util.ArrayList').$new();
      };
    });
  });

  console.log('[bypass] TrustManagerImpl hooked');
});
